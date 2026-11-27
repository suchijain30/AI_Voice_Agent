from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.screenings.schemas import ScreeningQuestion


class CandidateAgentContext(BaseModel):
    application_id: UUID
    name: str = Field(min_length=1, max_length=200)
    phone_number: str | None = Field(default=None, min_length=1, max_length=16)
    email: str | None = Field(default=None, max_length=254)
    stated_experience_years: float | None = Field(default=None, ge=0, le=80)
    skills: list[str] = Field(default_factory=list, max_length=100)
    location: str | None = Field(default=None, max_length=200)

    model_config = ConfigDict(extra="forbid")


class JobAgentContext(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20000)
    candidate_listed_skills: list[str] = Field(default_factory=list, max_length=100)
    candidate_location: str | None = Field(default=None, max_length=200)

    model_config = ConfigDict(extra="forbid")


class CandidateAnswerContext(BaseModel):
    question_key: str
    original_response: str | None = None
    normalized_value: object | None = None
    information_source: Literal["explicit", "inferred"] | None = None
    is_missing: bool

    @model_validator(mode="after")
    def validate_provenance(self):
        if self.is_missing and (self.original_response is not None or self.normalized_value is not None
                                or self.information_source is not None):
            raise ValueError("Missing information cannot contain an answer or provenance.")
        if not self.is_missing and self.information_source is None:
            raise ValueError("Recorded answers must preserve explicit or inferred provenance.")
        return self

    model_config = ConfigDict(extra="forbid")


class ScreeningAgentContext(BaseModel):
    session_id: UUID
    questions: list[ScreeningQuestion] = Field(min_length=1, max_length=50)
    existing_answers: list[CandidateAnswerContext] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_question_snapshot(self):
        keys = [question.question_key for question in self.questions]
        orders = [question.order for question in self.questions]
        if len(keys) != len(set(keys)) or len(orders) != len(set(orders)):
            raise ValueError("Screening questions must have unique keys and order values.")
        if keys != [item.question_key for item in sorted(self.questions, key=lambda item: item.order)]:
            raise ValueError("Screening questions must be ordered by their configured order.")
        if set(answer.question_key for answer in self.existing_answers) - set(keys):
            raise ValueError("Existing answers must refer to configured screening questions.")
        return self

    model_config = ConfigDict(extra="forbid")


class RecruitmentAgentInstructions(BaseModel):
    persona: str = Field(default="AI recruitment assistant", min_length=1, max_length=200)
    introduction: str = Field(default="Introduce yourself as an AI recruitment assistant and identify the configured role.", max_length=1000)
    purpose: str = Field(default="Explain that the call is to learn about the candidate's experience and interest in the role.", max_length=1000)
    conversation_style: str = Field(default="Be professional, warm, concise, and conversational. Ask one question at a time.", max_length=2000)
    language_behavior: str = Field(default="Use English, Hindi, or Hinglish naturally according to the candidate's language, when supported by the selected provider. Language quality is unverified until tested.", max_length=2000)
    language_options: list[Literal["English", "Hindi", "Hinglish"]] = Field(
        default_factory=lambda: ["English", "Hindi", "Hinglish"], min_length=1, max_length=3
    )
    question_rules: list[str] = Field(default_factory=lambda: [
        "Ask configured questions in order, one at a time.",
        "Ask relevant follow-ups only when needed and do not repeat information already answered.",
        "Allow corrections and preserve the candidate's latest explicit answer.",
    ], max_length=20)
    refusal_and_stop_handling: str = Field(default="Ask permission to continue; respect refusal or a request to stop and end politely.", max_length=1000)
    extraction_rules: str = Field(default="Capture requested fields only. Mark each as explicit, inferred, or unknown; never present an inference as candidate-stated fact.", max_length=2000)
    no_fabrication_rules: str = Field(default="Never invent experience, skills, compensation, notice period, location, availability, or other candidate information. Treat unknown values as unknown.", max_length=2000)
    unrelated_question_handling: str = Field(default="Answer unrelated questions briefly only when supported by supplied job context; otherwise say you do not have that information and return to screening if appropriate.", max_length=1500)
    closing: str = Field(default="Thank the candidate and explain that a recruiter will review the information; do not promise an outcome.", max_length=1000)

    @field_validator("question_rules")
    @classmethod
    def rules_not_blank(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("Instruction rules must not be blank.")
        return value

    @model_validator(mode="after")
    def unique_language_options(self):
        if len(self.language_options) != len(set(self.language_options)):
            raise ValueError("Language options must be unique.")
        return self

    model_config = ConfigDict(extra="forbid")


class RecruitmentAgentConfiguration(BaseModel):
    schema_version: Literal["1"] = "1"
    candidate: CandidateAgentContext
    job: JobAgentContext
    screening: ScreeningAgentContext
    instructions: RecruitmentAgentInstructions = Field(default_factory=RecruitmentAgentInstructions)
    extraction_fields: list[str] = Field(default_factory=lambda: [
        "role_interest", "total_experience", "relevant_experience", "skills",
        "current_compensation", "expected_compensation", "notice_period",
        "current_location", "work_location_preference", "interview_availability", "missing_information",
    ], min_length=1, max_length=30)

    @model_validator(mode="after")
    def ensure_no_duplicate_extraction_fields(self):
        if len(self.extraction_fields) != len(set(self.extraction_fields)):
            raise ValueError("Extraction field names must be unique.")
        return self

    model_config = ConfigDict(extra="forbid")
