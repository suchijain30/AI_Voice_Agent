from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.screenings.types import ScreeningSessionStatus


class ScreeningQuestion(BaseModel):
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    question_text: str = Field(min_length=1, max_length=1000)
    required: bool
    order: int = Field(ge=0)
    category: str = Field(min_length=1, max_length=80)
    follow_up_guidance: str | None = Field(default=None, max_length=2000)

    @field_validator("question_text", "category")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must contain non-whitespace characters.")
        return value


class ScreeningSessionCreate(BaseModel):
    candidate_id: UUID
    call_id: UUID | None = None
    questions: list[ScreeningQuestion] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_question_keys_and_orders(self):
        if self.questions is not None:
            keys = [question.question_key for question in self.questions]
            orders = [question.order for question in self.questions]
            if len(keys) != len(set(keys)):
                raise ValueError("Question keys must be unique within a screening session.")
            if len(orders) != len(set(orders)):
                raise ValueError("Question order values must be unique within a screening session.")
        return self


class ScreeningSessionStatusUpdate(BaseModel):
    status: ScreeningSessionStatus


InformationSource = Literal["explicit", "inferred"]


class ScreeningAnswerUpsert(BaseModel):
    original_response: str | None = Field(default=None, max_length=10000)
    normalized_value: Any | None = None
    information_source: InformationSource | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_missing: bool = False

    @model_validator(mode="after")
    def validate_missing_and_provenance(self):
        if self.is_missing:
            if any(
                value is not None
                for value in (self.original_response, self.normalized_value, self.information_source, self.confidence)
            ):
                raise ValueError("Missing answers cannot include response, extracted value, source, or confidence.")
            return self
        if self.original_response is None or not self.original_response.strip():
            raise ValueError("A non-missing answer requires the original candidate response.")
        if self.information_source is None:
            raise ValueError("Answered information must be marked explicit or inferred.")
        return self


class ScreeningAnswerRead(ScreeningAnswerUpsert):
    id: UUID
    session_id: UUID
    question_key: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


InterestLevel = Literal["interested", "not_interested", "uncertain", "not_asked"]
WorkArrangementCompatibility = Literal["compatible", "not_compatible", "unclear", "not_assessed"]
AdvisoryRecommendation = Literal["proceed_to_human_review", "request_more_information", "no_recommendation"]


class ScreeningEvaluationInput(BaseModel):
    total_experience_years: float | None = Field(default=None, ge=0, le=80)
    relevant_experience_years: float | None = Field(default=None, ge=0, le=80)
    skills: list[str] = Field(default_factory=list, max_length=100)
    current_compensation: str | None = Field(default=None, max_length=200)
    expected_compensation: str | None = Field(default=None, max_length=200)
    notice_period: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    work_arrangement_preference: str | None = Field(default=None, max_length=200)
    work_arrangement_compatibility: WorkArrangementCompatibility | None = None
    interest_level: InterestLevel = "not_asked"
    interview_availability: str | None = Field(default=None, max_length=500)
    field_sources: dict[str, InformationSource] = Field(default_factory=dict)
    missing_information: list[str] = Field(default_factory=list, max_length=100)
    screening_summary: str = Field(min_length=1, max_length=5000)
    advisory_recommendation: AdvisoryRecommendation = "no_recommendation"
    recommendation_reason: str = Field(min_length=1, max_length=2000)
    suggested_next_action: str = Field(min_length=1, max_length=1000)

    @field_validator("screening_summary", "recommendation_reason", "suggested_next_action")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must contain non-whitespace characters.")
        return value

    @field_validator("skills", "missing_information")
    @classmethod
    def reject_blank_list_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("List entries must contain non-whitespace characters.")
        return values

    @model_validator(mode="after")
    def relevant_experience_not_above_total(self):
        if (
            self.total_experience_years is not None
            and self.relevant_experience_years is not None
            and self.relevant_experience_years > self.total_experience_years
        ):
            raise ValueError("Relevant experience cannot exceed total experience.")
        field_names = {
            "total_experience_years": self.total_experience_years is not None,
            "relevant_experience_years": self.relevant_experience_years is not None,
            "skills": bool(self.skills),
            "current_compensation": self.current_compensation is not None,
            "expected_compensation": self.expected_compensation is not None,
            "notice_period": self.notice_period is not None,
            "location": self.location is not None,
            "work_arrangement_preference": self.work_arrangement_preference is not None,
            "work_arrangement_compatibility": self.work_arrangement_compatibility is not None,
            "interest_level": self.interest_level != "not_asked",
            "interview_availability": self.interview_availability is not None,
        }
        unknown = set(self.field_sources) - set(field_names)
        if unknown:
            raise ValueError(f"Unknown evaluation provenance fields: {', '.join(sorted(unknown))}.")
        missing_sources = [key for key, populated in field_names.items() if populated and key not in self.field_sources]
        if missing_sources:
            raise ValueError(f"Provide explicit or inferred provenance for: {', '.join(missing_sources)}.")
        return self


class ScreeningEvaluationRead(ScreeningEvaluationInput):
    id: UUID
    session_id: UUID
    candidate_name: str
    job_title: str
    created_at: datetime
    updated_at: datetime


class ScreeningSessionRead(BaseModel):
    id: UUID
    candidate_id: UUID
    call_id: UUID | None
    status: ScreeningSessionStatus
    questions: list[ScreeningQuestion]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    provider_transcript: str | None = None
    provider_summary: str | None = None
    provider_extracted_data: Any | None = None
    provider_call_duration_seconds: int | None = None

