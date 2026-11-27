from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.calls.types import CallStatus


class CallRead(BaseModel):
    id: UUID
    candidate_id: UUID
    provider: str
    provider_call_id: str | None
    status: CallStatus
    provider_outcome: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    ended_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CallEventRead(BaseModel):
    id: UUID
    call_id: UUID
    provider: str
    provider_event_id: str
    event_type: str
    status: CallStatus
    occurred_at: datetime | None
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BolnaSyncRead(BaseModel):
    call: CallRead
    result_available: bool


class MockEventRequest(BaseModel):
    provider_event_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=100)
    status: CallStatus
    occurred_at: datetime | None = None
