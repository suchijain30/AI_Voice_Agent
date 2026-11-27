from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.calls.providers import AmbiguousProviderOutcome, CallProvider, ProviderError, ProviderRejectedCall
from app.calls.types import (
    CallStatus,
    EventHandlingResult,
    NormalizedProviderEvent,
    ProviderCallRequest,
    TERMINAL_STATUSES,
)
from app.models import Call, CallEvent, Candidate
from app.models import ScreeningSession
from app.recruitment_agent.schemas import RecruitmentAgentConfiguration


class CallLifecycleError(Exception):
    pass


class CallExecutionDisabled(CallLifecycleError):
    pass


class CandidateNotFound(CallLifecycleError):
    pass


class CallNotFound(CallLifecycleError):
    pass


class IdempotencyConflict(CallLifecycleError):
    pass


class InvalidCallTransition(CallLifecycleError):
    pass


class ProviderEventConflict(CallLifecycleError):
    pass


class ProviderOperationError(CallLifecycleError):
    pass


class CallStorageError(CallLifecycleError):
    pass


class UnresolvedCallOutcome(CallLifecycleError):
    pass


_ALLOWED_TRANSITIONS = {
    CallStatus.QUEUED: {
        CallStatus.INITIATED,
        CallStatus.RINGING,
        CallStatus.IN_PROGRESS,
        CallStatus.FINALIZING,
        CallStatus.FAILED,
        CallStatus.DISCONNECTED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.CANCELED,
        CallStatus.RECONCILIATION_REQUIRED,
    },
    CallStatus.INITIATED: {
        CallStatus.RINGING,
        CallStatus.IN_PROGRESS,
        CallStatus.FINALIZING,
        CallStatus.DISCONNECTED,
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.CANCELED,
    },
    CallStatus.RINGING: {
        CallStatus.IN_PROGRESS,
        CallStatus.FINALIZING,
        CallStatus.DISCONNECTED,
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.CANCELED,
    },
    CallStatus.IN_PROGRESS: {
        CallStatus.COMPLETED,
        CallStatus.FINALIZING,
        CallStatus.DISCONNECTED,
        CallStatus.FAILED,
        CallStatus.CANCELED,
    },
    CallStatus.FINALIZING: {
        CallStatus.COMPLETED,
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.CANCELED,
    },
    CallStatus.RECONCILIATION_REQUIRED: {
        CallStatus.QUEUED,
        CallStatus.INITIATED,
        CallStatus.RINGING,
        CallStatus.IN_PROGRESS,
        CallStatus.FINALIZING,
        CallStatus.COMPLETED,
        CallStatus.DISCONNECTED,
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.CANCELED,
    },
}


class CallLifecycleService:
    def __init__(self, db: Session, provider: CallProvider, *, enabled: bool = False):
        self.db = db
        self.provider = provider
        self.enabled = enabled

    def create_call(
        self,
        candidate_id: UUID,
        idempotency_key: str,
        *,
        screening_session_id: UUID | None = None,
        agent_configuration: RecruitmentAgentConfiguration | None = None,
    ) -> tuple[Call, bool]:
        if not self.enabled:
            raise CallExecutionDisabled("Mock call execution is disabled.")

        existing = self.db.scalar(select(Call).where(Call.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.candidate_id != candidate_id or existing.provider != self.provider.name:
                raise IdempotencyConflict("This idempotency key was already used for another call request.")
            return existing, False

        candidate = self.db.get(Candidate, candidate_id)
        if candidate is None:
            raise CandidateNotFound("Candidate not found.")

        screening_session = None
        if screening_session_id is not None:
            screening_session = self.db.get(ScreeningSession, screening_session_id)
            if screening_session is None:
                raise CallNotFound("Screening session not found.")
            if screening_session.candidate_id != candidate_id:
                raise IdempotencyConflict("The screening session belongs to a different candidate.")
            if screening_session.call_id is not None:
                linked = self.db.get(Call, screening_session.call_id)
                if linked is not None:
                    if linked.provider == self.provider.name:
                        return linked, False
                    raise IdempotencyConflict("The screening session already has a call from another provider.")

        if screening_session_id is not None and self.provider.name == "bolna":
            previous_application_call = self.db.scalar(
                select(Call).where(Call.candidate_id == candidate_id, Call.provider == "bolna")
            )
            if previous_application_call is not None:
                raise IdempotencyConflict("A Bolna call already exists for this candidate application.")

        unresolved = self.db.scalar(
            select(Call.id).where(
                Call.candidate_id == candidate_id,
                Call.provider == self.provider.name,
                Call.status == CallStatus.RECONCILIATION_REQUIRED.value,
            )
        )
        if unresolved is not None:
            raise UnresolvedCallOutcome("A previous call outcome for this candidate and provider requires reconciliation.")

        call = Call(
            candidate_id=candidate.id,
            provider=self.provider.name,
            idempotency_key=idempotency_key,
            status=CallStatus.QUEUED.value,
            configuration_metadata={"provider_outcome": "pending"},
        )
        self.db.add(call)
        try:
            if screening_session is not None:
                self.db.flush()
                screening_session.call_id = call.id
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raced_call = self.db.scalar(select(Call).where(Call.idempotency_key == idempotency_key))
            if raced_call is not None:
                if raced_call.candidate_id != candidate_id or raced_call.provider != self.provider.name:
                    raise IdempotencyConflict("This idempotency key was already used for another call request.") from exc
                return raced_call, False
            if screening_session_id is not None and self.provider.name == "bolna":
                raced_application_call = self.db.scalar(
                    select(Call).where(Call.candidate_id == candidate_id, Call.provider == "bolna")
                )
                if raced_application_call is not None:
                    raise IdempotencyConflict("A Bolna call already exists for this candidate application.") from exc
            raise CallStorageError("Could not create call record.") from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise CallStorageError("Could not create call record.") from exc

        request = ProviderCallRequest(
            call_id=call.id,
            idempotency_key=idempotency_key,
            # Providers require a canonical dialable address; do not forward the
            # presentation-form phone value entered in the intake form.
            recipient_phone_number=candidate.normalized_phone_number,
            job_title=candidate.job_title,
            job_description=candidate.job_description,
            agent_configuration=agent_configuration,
        )
        try:
            provider_call_id = self.provider.start_call(request)
        except AmbiguousProviderOutcome:
            self._record_creation_outcome(call, "ambiguous", CallStatus.RECONCILIATION_REQUIRED)
            raise ProviderOperationError(
                "Provider call outcome is ambiguous; reconciliation is required. No retry was attempted."
            ) from None
        except ProviderRejectedCall as exc:
            self._record_creation_outcome(call, "rejected", CallStatus.FAILED)
            raise ProviderOperationError(str(exc)) from None
        except ProviderError as exc:
            self._record_creation_outcome(call, "rejected", CallStatus.FAILED)
            raise ProviderOperationError("Provider rejected the call request.") from None
        except Exception:
            # Unknown exceptions are conservatively treated as ambiguous.
            self._record_creation_outcome(call, "ambiguous", CallStatus.RECONCILIATION_REQUIRED)
            raise ProviderOperationError(
                "Provider call outcome is ambiguous; reconciliation is required. No retry was attempted."
            ) from None

        call.provider_call_id = provider_call_id
        if screening_session is not None:
            screening_session.call_id = call.id
        call.configuration_metadata = {"provider_outcome": "accepted"}
        try:
            self.db.commit()
            self.db.refresh(call)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise CallStorageError("Could not save provider call reference.") from exc
        return call, True

    def _record_creation_outcome(self, call: Call, outcome: str, status: CallStatus) -> None:
        call.status = status.value
        call.configuration_metadata = {"provider_outcome": outcome}
        if status in TERMINAL_STATUSES:
            call.ended_at = datetime.now(timezone.utc)
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise CallStorageError("Could not record provider call outcome.") from exc

    def reconcile_ambiguous_call(
        self,
        call_id: UUID,
        *,
        provider_call_id: str | None,
        status: CallStatus | None = None,
    ) -> Call:
        """Record an explicit reconciliation result; this method never calls a provider."""
        call = self.get_call(call_id)
        if call.status != CallStatus.RECONCILIATION_REQUIRED.value:
            raise InvalidCallTransition("Only calls requiring reconciliation can be reconciled.")

        if provider_call_id is None:
            if status is not None:
                raise ValueError("A status cannot be supplied when reconciliation confirms no provider call exists.")
            call.status = CallStatus.FAILED.value
            call.ended_at = datetime.now(timezone.utc)
            outcome = "reconciled_not_created"
        else:
            if not provider_call_id.strip() or status is None or status == CallStatus.RECONCILIATION_REQUIRED:
                raise ValueError("Reconciliation of a created call requires its provider ID and a known status.")
            call.provider_call_id = provider_call_id
            call.status = status.value
            if status in {CallStatus.INITIATED, CallStatus.RINGING, CallStatus.IN_PROGRESS} and call.started_at is None:
                call.started_at = datetime.now(timezone.utc)
            if status in TERMINAL_STATUSES:
                call.ended_at = datetime.now(timezone.utc)
            outcome = "reconciled_created"

        call.configuration_metadata = {"provider_outcome": outcome}
        try:
            self.db.commit()
            self.db.refresh(call)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise CallStorageError("Could not save reconciliation result.") from exc
        return call

    def get_call(self, call_id: UUID) -> Call:
        call = self.db.get(Call, call_id)
        if call is None:
            raise CallNotFound("Call not found.")
        return call

    def handle_event(self, event: NormalizedProviderEvent) -> EventHandlingResult:
        if event.provider != self.provider.name:
            raise ProviderEventConflict("Event provider does not match this lifecycle service.")

        existing_event = self.db.scalar(
            select(CallEvent).where(
                CallEvent.provider == event.provider,
                CallEvent.provider_event_id == event.provider_event_id,
            )
        )
        if existing_event is not None:
            if existing_event.call_id != self.db.scalar(
                select(Call.id).where(
                    Call.provider == event.provider,
                    Call.provider_call_id == event.provider_call_id,
                )
            ):
                raise ProviderEventConflict("Provider event ID is already associated with another call.")
            call = self.get_call(existing_event.call_id)
            return EventHandlingResult(call_id=call.id, status=CallStatus(call.status), duplicate=True)

        call = self.db.scalar(
            select(Call).where(Call.provider == event.provider, Call.provider_call_id == event.provider_call_id)
        )
        if call is None:
            raise CallNotFound("No call matches the provider call ID.")

        current_status = CallStatus(call.status)
        next_status = CallStatus(event.status)
        if next_status != current_status and next_status not in _ALLOWED_TRANSITIONS.get(current_status, set()):
            raise InvalidCallTransition(f"Call cannot transition from {current_status.value} to {next_status.value}.")

        call.status = next_status.value
        event_time = event.occurred_at or datetime.now(timezone.utc)
        if next_status in {CallStatus.INITIATED, CallStatus.RINGING, CallStatus.IN_PROGRESS} and call.started_at is None:
            call.started_at = event_time
        if next_status in TERMINAL_STATUSES:
            call.ended_at = event_time
        self.db.add(
            CallEvent(
                call_id=call.id,
                provider=event.provider,
                provider_event_id=event.provider_event_id,
                event_type=event.event_type,
                status=next_status.value,
                occurred_at=event.occurred_at,
            )
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            duplicate = self.db.scalar(
                select(CallEvent).where(
                    CallEvent.provider == event.provider,
                    CallEvent.provider_event_id == event.provider_event_id,
                )
            )
            if duplicate is not None and duplicate.call_id == call.id:
                persisted_call = self.get_call(call.id)
                return EventHandlingResult(call_id=persisted_call.id, status=CallStatus(persisted_call.status), duplicate=True)
            raise ProviderEventConflict("Provider event could not be recorded safely.") from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise CallStorageError("Could not update call state.") from exc
        return EventHandlingResult(call_id=call.id, status=next_status, duplicate=False)
