from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.conversations.orchestrator import ResponseDisposition
from app.conversations.types import ConversationState, TurnSpeaker, TurnType


class ConversationStartRequest(BaseModel):
    max_clarification_attempts: int = Field(default=2, ge=1, le=5)


class CandidateResponseRequest(BaseModel):
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    disposition: ResponseDisposition | None = None
    intelligence_scenario: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,63}$", max_length=64)
    response_text: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def validate_response_for_disposition(self):
        if (self.disposition is None) == (self.intelligence_scenario is None):
            raise ValueError("Provide exactly one of disposition or intelligence_scenario.")
        if self.intelligence_scenario is not None:
            return self
        requires_text = {
            ResponseDisposition.ANSWER,
            ResponseDisposition.UNCLEAR,
            ResponseDisposition.CLARIFICATION,
        }
        if self.disposition in requires_text and (self.response_text is None or not self.response_text.strip()):
            raise ValueError("This response disposition requires non-empty response_text.")
        if self.disposition == ResponseDisposition.NO_RESPONSE and self.response_text not in (None, ""):
            raise ValueError("no_response must not include response_text.")
        return self


class AgentPromptRead(BaseModel):
    question_key: str
    question_text: str
    spoken_wording: str
    follow_up_guidance: str | None
    required: bool
    question_index: int
    total_questions: int


class ConversationRead(BaseModel):
    id: UUID
    screening_session_id: UUID
    state: ConversationState
    current_question_key: str | None
    clarification_attempts: int
    max_clarification_attempts: int
    current_prompt: AgentPromptRead | None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None


class ConversationTurnRead(BaseModel):
    id: UUID
    conversation_id: UUID
    turn_number: int
    speaker: TurnSpeaker
    message_text: str
    question_key: str | None
    turn_type: TurnType
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ConversationInteractionRead(BaseModel):
    conversation: ConversationRead
    outcome: str
    prompt: AgentPromptRead | None
    interpretation: dict[str, Any] | None = None
    used_safe_fallback: bool = False
    fallback_reason: str | None = None


