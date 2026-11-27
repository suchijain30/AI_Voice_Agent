from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CallStatus(StrEnum):
    QUEUED = "queued"
    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    CANCELED = "canceled"
    RECONCILIATION_REQUIRED = "reconciliation_required"


CALL_STATUSES = tuple(status.value for status in CallStatus)
TERMINAL_STATUSES = frozenset(
    {
        CallStatus.COMPLETED,
        CallStatus.DISCONNECTED,
        CallStatus.FAILED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.CANCELED,
    }
)


@dataclass(frozen=True)
class ProviderCallRequest:
    call_id: UUID
    idempotency_key: str
    recipient_phone_number: str
    job_title: str
    job_description: str
    # Provider-neutral M8 context, consumed only by adapters that support it.
    agent_configuration: object | None = None


@dataclass(frozen=True)
class NormalizedProviderEvent:
    provider: str
    provider_call_id: str
    provider_event_id: str
    event_type: str
    status: CallStatus
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class EventHandlingResult:
    call_id: UUID
    status: CallStatus
    duplicate: bool
