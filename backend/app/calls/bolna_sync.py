"""Bolna retrieval and webhook-processing foundation (no HTTP ingress here)."""

import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.calls.bolna import BolnaAdapter, BolnaExecution
from app.calls.providers import ProviderRetrievalError
from app.calls.service import CallLifecycleService, CallNotFound, CallStorageError
from app.calls.types import CallStatus
from app.models import Call, ScreeningSession
from app.config import BolnaSettings
from app.screenings.extraction import ScreeningResultProcessor

MAX_PERSISTED_RESULTS_BYTES = 256_000


class BolnaWebhookAuthenticationError(Exception):
    pass


def verify_bolna_webhook_secret(configured: BolnaSettings, supplied: str | None) -> None:
    """Validate a configured shared custom-header value in constant time.

    This helper is not wired to a route. Bolna signature and event-delivery
    guarantees are unverified, so internet-facing webhook activation remains off.
    """
    if configured.bolna_webhook_secret is None or supplied is None:
        raise BolnaWebhookAuthenticationError("Bolna webhook authentication is not configured.")
    expected = configured.bolna_webhook_secret.get_secret_value().encode()
    if not hmac.compare_digest(expected, supplied.encode()):
        raise BolnaWebhookAuthenticationError("Bolna webhook authentication failed.")


class BolnaSyncService:
    def __init__(self, db: Session, adapter: BolnaAdapter):
        self.db = db
        self.adapter = adapter
        self.lifecycle = CallLifecycleService(db, adapter, enabled=True)

    @staticmethod
    def list_stale_finalizing_calls(
        db: Session,
        *,
        stale_after_seconds: int,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[Call]:
        """List calls unchanged in finalizing beyond the configured age.

        `Call.updated_at` is changed by a new accepted lifecycle event, but not
        by duplicate event delivery or a failed retrieval. This endpoint is
        read-only; it never contacts Bolna or starts a call.
        """
        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(seconds=stale_after_seconds)
        return list(db.scalars(
            select(Call)
            .where(
                Call.provider == "bolna",
                Call.status == CallStatus.FINALIZING.value,
                Call.updated_at <= cutoff,
            )
            .order_by(Call.updated_at, Call.id)
            .limit(limit)
        ).all())

    def sync_call(self, call_id: UUID) -> tuple[Call, bool]:
        call = self.db.get(Call, call_id)
        if call is None:
            raise CallNotFound("Call not found.")
        if call.provider != "bolna" or not call.provider_call_id:
            raise ProviderRetrievalError("This call does not have a retrievable Bolna execution.")
        execution = self.adapter.get_execution(call.provider_call_id)
        normalized_event = self.adapter.execution_event(call.provider_call_id, execution, None)
        result_available = normalized_event.status == CallStatus.COMPLETED
        updated, _ = self._apply_execution(call.provider_call_id, execution, occurred_at=None)
        return updated, result_available

    def process_webhook(
        self,
        payload: Mapping[str, Any],
        *,
        settings: BolnaSettings,
        supplied_secret: str | None,
    ) -> tuple[Call, bool]:
        verify_bolna_webhook_secret(settings, supplied_secret)
        execution_id, execution, occurred_at = self.adapter.parse_webhook_payload(payload)
        return self._apply_execution(execution_id, execution, occurred_at=occurred_at)

    def _apply_execution(
        self, execution_id: str, execution: BolnaExecution, *, occurred_at: datetime | None
    ) -> tuple[Call, bool]:
        event = self.adapter.execution_event(execution_id, execution, occurred_at)
        # A finalized execution may be fetched after its intermediate webhook
        # was missed. Bolna documents call-disconnected before completed, so
        # record that nonterminal progression rather than weakening generic
        # lifecycle transitions or jumping directly from queued to completed.
        if event.status == CallStatus.COMPLETED:
            current_call = self.db.scalar(
                select(Call).where(Call.provider == "bolna", Call.provider_call_id == execution_id)
            )
            if current_call is not None and CallStatus(current_call.status) in {
                CallStatus.QUEUED, CallStatus.INITIATED, CallStatus.RINGING,
                CallStatus.IN_PROGRESS, CallStatus.RECONCILIATION_REQUIRED,
            }:
                interim = self.adapter.finalizing_event(execution_id, occurred_at)
                self.lifecycle.handle_event(interim)
        result = self.lifecycle.handle_event(event)
        call = self.db.get(Call, result.call_id)
        if event.status == CallStatus.COMPLETED:
            session = self.db.scalar(select(ScreeningSession).where(ScreeningSession.call_id == call.id))
            if session is not None:
                try:
                    encoded = json.dumps(
                        {
                            "transcript": execution.transcript,
                            "summary": execution.summary,
                            "extracted_data": execution.extracted_data,
                        }, ensure_ascii=False
                    ).encode()
                    if len(encoded) > MAX_PERSISTED_RESULTS_BYTES:
                        raise ProviderRetrievalError("Bolna screening result exceeds the configured storage limit.")
                    session.provider_transcript = execution.transcript
                    session.provider_summary = execution.summary
                    session.provider_extracted_data = execution.extracted_data
                    session.provider_call_duration_seconds = (
                        int(execution.duration) if execution.duration is not None else None
                    )
                    self.db.commit()
                    ScreeningResultProcessor(self.db).process_provider_results(session.id)
                except ProviderRetrievalError:
                    self.db.rollback()
                    raise
                except (SQLAlchemyError, TypeError, ValueError):
                    self.db.rollback()
                    raise CallStorageError("Could not save Bolna screening results.") from None
        return call, result.duplicate
