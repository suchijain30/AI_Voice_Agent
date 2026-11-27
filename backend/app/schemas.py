import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.normalization import normalize_phone_number

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CandidateCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone_number: str = Field(max_length=32)
    email: str | None = Field(default=None, max_length=254)
    job_title: str = Field(min_length=1, max_length=200)
    job_description: str = Field(min_length=1, max_length=10000)
    years_of_experience: Decimal | None = Field(default=None, ge=0, le=80, max_digits=4, decimal_places=1)
    skills: list[str] = Field(default_factory=list, max_length=100)
    location: str | None = Field(default=None, max_length=200)

    @field_validator("full_name", "job_title", "job_description", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("This field cannot be blank.")
        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        normalize_phone_number(value)
        return value

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 254 or not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("location", mode="before")
    @classmethod
    def normalize_location(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value or None

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skills(cls, value):
        if isinstance(value, str):
            value = value.split(",")
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Skills must be a list of skill names.")
        return [skill.strip() for skill in value if isinstance(skill, str) and skill.strip()]


class CandidateRead(BaseModel):
    id: UUID
    full_name: str
    phone_number: str
    email: str | None
    job_title: str
    job_description: str
    years_of_experience: Decimal | None
    skills: list[str]
    location: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
