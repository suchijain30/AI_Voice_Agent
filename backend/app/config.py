from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "AI HR Recruitment Voice Agent API"
    app_env: str = "development"
    database_url: str = Field(min_length=1)
    cors_origins: str = "http://localhost:5173"
    mock_calls_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    @field_validator("database_url")
    @classmethod
    def require_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_URL must not be empty.")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


class BolnaSettings(BaseSettings):
    """Loaded only when the Bolna adapter is explicitly constructed."""

    bolna_calls_enabled: bool = False
    bolna_api_key: SecretStr | None = None
    
    
    bolna_agent_id: str | None = None
    bolna_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    bolna_finalizing_timeout_seconds: int = Field(default=900, ge=60, le=86400)
    bolna_webhook_secret: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    @field_validator("bolna_api_key", mode="before")
    @classmethod
    def normalize_bolna_api_key(cls, value):
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        value = str(value).strip()
        return SecretStr(value) if value else None

    @field_validator("bolna_agent_id", mode="before")
    @classmethod
    def normalize_bolna_agent_id(cls, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("bolna_webhook_secret", mode="before")
    @classmethod
    def normalize_bolna_webhook_secret(cls, value):
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        value = str(value).strip()
        return SecretStr(value) if value else None

    @model_validator(mode="after")
    def validate_bolna_configuration(self):
        if self.bolna_calls_enabled and (self.bolna_api_key is None or self.bolna_agent_id is None):
            raise ValueError("BOLNA_API_KEY and BOLNA_AGENT_ID are required when BOLNA_CALLS_ENABLED is true.")
        return self


class RetellSettings(BaseSettings):
    """Loaded only when the Retell adapter is explicitly constructed."""

    retell_calls_enabled: bool = False
    retell_api_key: SecretStr | None = None
    retell_from_number: str | None = None
    retell_agent_id: str | None = None
    retell_timeout_seconds: float = Field(default=10.0, gt=0, le=120)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    @field_validator("retell_api_key", mode="before")
    @classmethod
    def normalize_retell_api_key(cls, value):
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        value = str(value).strip()
        return SecretStr(value) if value else None

    @field_validator("retell_from_number", "retell_agent_id", mode="before")
    @classmethod
    def normalize_optional_retell_values(cls, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def validate_retell_configuration(self):
        if self.retell_calls_enabled and (self.retell_api_key is None or self.retell_from_number is None):
            raise ValueError("RETELL_API_KEY and RETELL_FROM_NUMBER are required when RETELL_CALLS_ENABLED is true.")
        return self


class IntelligenceSettings(BaseSettings):
    """Non-secret configuration for the offline intelligence boundary."""

    intelligence_provider: Literal["mock"] = "mock"
    intelligence_model: str = "mock-fixture-v1"
    intelligence_api_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    intelligence_max_response_chars: int = Field(default=4000, ge=1, le=10000)
    intelligence_max_context_turns: int = Field(default=8, ge=0, le=50)
    intelligence_max_context_chars: int = Field(default=16000, ge=1000, le=50000)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    @field_validator("intelligence_model")
    @classmethod
    def require_model_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("INTELLIGENCE_MODEL must not be empty.")
        return value


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        if any(error.get("loc") == ("database_url",) for error in exc.errors()):
            raise RuntimeError(
                "DATABASE_URL is required. Set it in the process environment or the repository-root .env file."
            ) from exc
        raise
