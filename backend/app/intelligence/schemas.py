from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.conversations.orchestrator import ResponseDisposition


InformationSource = Literal["explicit", "inferred"]


class InterpretationTurn(BaseModel):
    speaker: Literal["agent", "candidate", "system"]
    message_text: str = Field(max_length=10000)
    question_key: str | None = Field(default=None, max_length=64)
    turn_type: str = Field(max_length=24)


class InterpretationContext(BaseModel):
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    question_text: str = Field(min_length=1, max_length=1000)
    question_follow_up_guidance: str | None = Field(default=None, max_length=2000)
    question_category: str = Field(min_length=1, max_length=80)
    question_required: bool
    raw_response: str | None = Field(default=None, max_length=10000)
    job_title: str = Field(min_length=1, max_length=200)
    job_description_context: str | None = Field(default=None, max_length=4000)
    previous_turns: list[InterpretationTurn] = Field(default_factory=list, max_length=50)
    conversation_state: str = Field(min_length=1, max_length=32)
    clarification_attempt_count: int = Field(ge=0, le=5)
    max_clarification_attempts: int = Field(ge=1, le=5)
    model_config = ConfigDict(extra="forbid")


class ResponseInterpretation(BaseModel):
    original_response: str | None = Field(default=None, max_length=10000)
    disposition: ResponseDisposition
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    extracted_answer: str | None = Field(default=None, max_length=10000)
    normalized_answer: Any | None = None
    clarification_needed: bool = False
    clarification_reason: str | None = Field(default=None, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    information_source: InformationSource | None = None
    is_missing: bool = False
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_interpretation_consistency(self):
        if self.normalized_answer is not None and self.extracted_answer is None:
            raise ValueError("A normalized answer requires an extracted answer.")
        if self.clarification_needed and not self.clarification_reason:
            raise ValueError("Clarification-required interpretations need a reason.")

        if self.disposition in {ResponseDisposition.ANSWER, ResponseDisposition.CLARIFICATION}:
            if self.is_missing or self.clarification_needed:
                raise ValueError("A clear answer cannot be missing or require clarification.")
            if self.original_response is None or not self.original_response.strip():
                raise ValueError("A clear answer requires the original candidate response.")
            if self.information_source is None:
                raise ValueError("A clear answer must be marked explicit or inferred.")
        else:
            if not self.is_missing:
                raise ValueError("A non-answer disposition must be marked missing/unanswered.")
            if any(
                value is not None
                for value in (self.extracted_answer, self.normalized_answer, self.information_source)
            ):
                raise ValueError("A missing answer cannot contain extracted values or provenance.")

        if self.disposition == ResponseDisposition.UNCLEAR:
            if not self.clarification_needed:
                raise ValueError("Unclear responses must request clarification.")
        elif self.clarification_needed:
            raise ValueError("Only unclear responses may request clarification in this contract.")
        return self

