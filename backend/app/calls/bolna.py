"""Bolna API adapter. All HTTP is injectable so tests remain completely offline."""

import json
import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.config import BolnaSettings
from app.calls.providers import (
    AmbiguousProviderOutcome,
    ProviderDisabled,
    ProviderRejectedCall,
    ProviderRetrievalError,
    UnknownProviderStatus,
)
from app.calls.types import CallStatus, NormalizedProviderEvent, ProviderCallRequest
from app.recruitment_agent.schemas import RecruitmentAgentConfiguration

BOLNA_CALL_URL = "https://api.bolna.ai/call"
BOLNA_EXECUTION_URL = "https://api.bolna.ai/executions/{}"
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")

_BOLNA_STATUS_MAP = {
    "queued": CallStatus.QUEUED,
    "initiated": CallStatus.INITIATED,
    "ringing": CallStatus.RINGING,
    "in-progress": CallStatus.IN_PROGRESS,
    "call-disconnected": CallStatus.FINALIZING,
    "completed": CallStatus.COMPLETED,
    "no-answer": CallStatus.NO_ANSWER,
    "busy": CallStatus.BUSY,
    "failed": CallStatus.FAILED,
    "canceled": CallStatus.CANCELED,
    "stopped": CallStatus.CANCELED,
    "error": CallStatus.FAILED,
    "balance-low": CallStatus.FAILED,
}


def normalize_bolna_status(value: str) -> CallStatus:
    """Normalize only statuses listed in the project's official-doc evidence."""
    if not isinstance(value, str):
        raise UnknownProviderStatus("Bolna returned an unsupported call status.")
    try:
        return _BOLNA_STATUS_MAP[value]
    except KeyError:
        raise UnknownProviderStatus("Bolna returned an unsupported call status.") from None


class BolnaExecution(BaseModel):
    """Small allowlisted view of execution fields documented for retrieval."""

    status: str = Field(min_length=1, max_length=64)
    transcript: str | None = Field(default=None, max_length=200_000)
    extracted_data: dict[str, Any] | list[Any] | None = None
    duration: float | None = Field(default=None, ge=0)
    summary: str | None = Field(default=None, max_length=20_000)

    model_config = ConfigDict(extra="ignore")


def bolna_event_id(execution_id: str, status: str, occurred_at: datetime | None) -> str:
    stable_input = f"{execution_id}|{status}|{occurred_at.isoformat() if occurred_at else ''}"
    return "bolna-" + hashlib.sha256(stable_input.encode()).hexdigest()


def bolna_user_data(configuration: RecruitmentAgentConfiguration) -> dict[str, str]:
    """Map M8 context to documented Bolna `user_data` substitution values.

    Values are strings because Bolna consumes these as template substitutions.
    Phone and email are deliberately excluded; the phone is used only as the
    required recipient_phone_number in the server-side call request.
    """
    validated = RecruitmentAgentConfiguration.model_validate(configuration.model_dump(mode="python"))
    questions = [
        {
            "question_key": question.question_key,
            "question": question.question_text,
            "required": question.required,
            "order": question.order,
            "category": question.category,
            "follow_up_guidance": question.follow_up_guidance,
        }
        for question in validated.screening.questions
    ]
    instructions = validated.instructions.model_dump(mode="json")
    user_data = {
        "candidate_name": validated.candidate.name,
        "job_title": validated.job.title,
        "job_description": validated.job.description,
        "screening_questions": json.dumps(questions, ensure_ascii=False, separators=(",", ":")),
        "agent_instructions": json.dumps(instructions, ensure_ascii=False, separators=(",", ":")),
        "candidate_context": json.dumps(
            {
                "stated_experience_years": validated.candidate.stated_experience_years,
                "skills": validated.candidate.skills,
                "location": validated.candidate.location,
                "existing_answers": [answer.model_dump(mode="json") for answer in validated.screening.existing_answers],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    return user_data


class BolnaAdapter:
    """Bolna call and execution adapter; never retries call creation."""

    name = "bolna"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        agent_id: str,
        timeout_seconds: float = 10.0,
        enabled: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("BOLNA_API_KEY is required.")
        if not agent_id.strip():
            raise ValueError("BOLNA_AGENT_ID is required.")
        self._api_key = api_key
        self._agent_id = agent_id.strip()
        self._enabled = enabled
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    @classmethod
    def from_settings(cls, settings: BolnaSettings, *, client: httpx.Client | None = None) -> "BolnaAdapter":
        if not settings.bolna_calls_enabled:
            raise ProviderDisabled("Bolna adapter is disabled by configuration.")
        assert settings.bolna_api_key is not None and settings.bolna_agent_id is not None
        return cls(
            api_key=settings.bolna_api_key,
            agent_id=settings.bolna_agent_id,
            timeout_seconds=settings.bolna_timeout_seconds,
            enabled=True,
            client=client,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    def start_call(self, request: ProviderCallRequest) -> str:
        if not self._enabled:
            raise ProviderDisabled("Bolna adapter is disabled.")

        payload: dict[str, Any] = {
            "agent_id": self._agent_id,
            "recipient_phone_number": request.recipient_phone_number,
        }
        if request.agent_configuration is not None:
            try:
                configuration = RecruitmentAgentConfiguration.model_validate(
                    request.agent_configuration.model_dump(mode="python")
                )
                payload["user_data"] = bolna_user_data(configuration)
            except (AttributeError, ValidationError, TypeError, ValueError):
                raise ProviderRejectedCall("Recruitment call context is invalid.") from None
        # No retry_config: Bolna call-creation idempotency is not documented.
        try:
            response = self._client.post(BOLNA_CALL_URL, json=payload, headers=self._headers())
        except httpx.RequestError:
            raise AmbiguousProviderOutcome(
                "Bolna call creation outcome is uncertain; reconciliation is required."
            ) from None
        self._raise_create_error(response)
        try:
            body = response.json()
        except (ValueError, TypeError):
            raise AmbiguousProviderOutcome(
                "Bolna returned an unreadable success response; reconciliation is required."
            ) from None
        if not isinstance(body, dict):
            raise AmbiguousProviderOutcome(
                "Bolna returned an invalid response without a usable execution_id; reconciliation is required."
            )
        execution_id = body.get("execution_id")
        if not isinstance(execution_id, str) or not _UUID_RE.fullmatch(execution_id):
            raise AmbiguousProviderOutcome(
                "Bolna success response did not contain a valid execution_id; reconciliation is required."
            )
        if not isinstance(body.get("status"), str):
            raise AmbiguousProviderOutcome(
                "Bolna success response did not contain a usable status; reconciliation is required."
            )
        try:
            creation_status = normalize_bolna_status(body["status"])
        except UnknownProviderStatus:
            raise AmbiguousProviderOutcome(
                "Bolna returned an unknown creation status; reconciliation is required."
            ) from None
        if creation_status != CallStatus.QUEUED:
            raise AmbiguousProviderOutcome(
                "Bolna returned an unexpected creation status; reconciliation is required."
            )
        return execution_id

    @staticmethod
    def _raise_create_error(response: httpx.Response) -> None:
        if 200 <= response.status_code < 300:
            return
        if response.status_code in {400, 401, 422}:
            if response.status_code == 401:
                raise ProviderRejectedCall("Bolna authentication failed.")
            raise ProviderRejectedCall(f"Bolna rejected the call request (HTTP {response.status_code}).")
        # No automatic resend: provider acceptance may be uncertain.
        raise AmbiguousProviderOutcome(
            f"Bolna call creation returned HTTP {response.status_code}; reconciliation is required."
        )

    def get_execution(self, execution_id: str) -> BolnaExecution:
        if not self._enabled:
            raise ProviderDisabled("Bolna adapter is disabled.")
        if not _UUID_RE.fullmatch(execution_id):
            raise ProviderRetrievalError("Bolna execution identifier is invalid.")
        url = BOLNA_EXECUTION_URL.format(quote(execution_id, safe=""))
        try:
            response = self._client.get(url, headers=self._headers())
        except httpx.RequestError:
            raise ProviderRetrievalError("Bolna execution retrieval failed; retry retrieval explicitly.") from None
        if response.status_code in {400, 401, 403, 404, 422}:
            message = "Bolna execution retrieval authentication failed." if response.status_code == 401 else "Bolna execution could not be retrieved."
            raise ProviderRetrievalError(message)
        if not 200 <= response.status_code < 300:
            raise ProviderRetrievalError(f"Bolna execution retrieval returned HTTP {response.status_code}.")
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError
            result = BolnaExecution.model_validate(body)
            normalize_bolna_status(result.status)
            return result
        except (ValueError, TypeError, ValidationError, UnknownProviderStatus):
            raise ProviderRetrievalError("Bolna returned an invalid or unsupported execution response.") from None

    @staticmethod
    def parse_webhook_payload(payload: Mapping[str, Any]) -> tuple[str, BolnaExecution, datetime | None]:
        """Validate documented execution-shaped webhook data; not an ingress handler."""
        try:
            execution = BolnaExecution.model_validate(payload)
            execution_id = payload.get("execution_id")
            occurred_at = payload.get("updated_at")
            if isinstance(occurred_at, str):
                occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            if occurred_at is not None and not isinstance(occurred_at, datetime):
                raise ValueError
            normalize_bolna_status(execution.status)
            if not isinstance(execution_id, str):
                raise ValueError
            UUID(execution_id)
        except Exception:
            raise ProviderRetrievalError("Bolna webhook payload is invalid or unsupported.") from None
        return execution_id, execution, occurred_at

    @staticmethod
    def execution_event(
        execution_id: str, execution: BolnaExecution, occurred_at: datetime | None
    ) -> NormalizedProviderEvent:
        status = normalize_bolna_status(execution.status)
        return NormalizedProviderEvent(
            provider="bolna",
            provider_call_id=execution_id,
            provider_event_id=bolna_event_id(execution_id, execution.status, occurred_at),
            event_type=f"execution.{execution.status}",
            status=status,
            occurred_at=occurred_at,
        )

    @staticmethod
    def finalizing_event(execution_id: str, occurred_at: datetime | None) -> NormalizedProviderEvent:
        return NormalizedProviderEvent(
            provider="bolna",
            provider_call_id=execution_id,
            provider_event_id=bolna_event_id(execution_id, "call-disconnected", occurred_at),
            event_type="execution.call-disconnected",
            status=CallStatus.FINALIZING,
            occurred_at=occurred_at,
        )
