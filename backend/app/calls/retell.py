from typing import Any

import httpx
from pydantic import SecretStr

from app.calls.providers import (
    AmbiguousProviderOutcome,
    ProviderDisabled,
    ProviderRejectedCall,
    UnknownProviderStatus,
)
from app.calls.types import CallStatus, ProviderCallRequest
from app.config import RetellSettings

RETELL_BASE_URL = "https://api.retellai.com"
RETELL_CREATE_PHONE_CALL_URL = f"{RETELL_BASE_URL}/v2/create-phone-call"

_RETELL_STATUS_MAP = {
    "registered": CallStatus.QUEUED,
    "not_connected": CallStatus.NO_ANSWER,
    "ongoing": CallStatus.IN_PROGRESS,
    "ended": CallStatus.COMPLETED,
    "error": CallStatus.FAILED,
}


def _is_e164(value: str) -> bool:
    """Check the documented E.164 shape without attempting region-specific parsing."""
    if not isinstance(value, str) or not value.startswith("+"):
        return False
    digits = value[1:]
    return digits.isascii() and digits.isdigit() and 2 <= len(digits) <= 15 and digits[0] != "0"


def normalize_retell_status(value: str) -> CallStatus:
    """Map only Retell's documented call status values to lifecycle statuses."""
    if not isinstance(value, str):
        raise UnknownProviderStatus("Retell returned an unsupported call status.")
    try:
        return _RETELL_STATUS_MAP[value]
    except KeyError:
        raise UnknownProviderStatus("Retell returned an unsupported call status.") from None


class RetellAdapter:
    """Offline-testable Retell call adapter; disabled by default and never retries."""

    name = "retell"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        from_number: str,
        agent_id: str | None = None,
        timeout_seconds: float = 10.0,
        enabled: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("RETELL_API_KEY is required.")
        if not _is_e164(from_number):
            raise ValueError("RETELL_FROM_NUMBER must use E.164 format.")
        self._api_key = api_key
        self._from_number = from_number
        self._agent_id = agent_id.strip() if agent_id else None
        self._enabled = enabled
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    @classmethod
    def from_settings(
        cls, settings: RetellSettings, *, client: httpx.Client | None = None
    ) -> "RetellAdapter":
        if not settings.retell_calls_enabled:
            raise ProviderDisabled("Retell adapter is disabled by configuration.")
        assert settings.retell_api_key is not None and settings.retell_from_number is not None
        return cls(
            api_key=settings.retell_api_key,
            from_number=settings.retell_from_number,
            agent_id=settings.retell_agent_id,
            timeout_seconds=settings.retell_timeout_seconds,
            enabled=True,
            client=client,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def start_call(self, request: ProviderCallRequest) -> str:
        if not self._enabled:
            raise ProviderDisabled("Retell adapter is disabled.")
        if not _is_e164(request.recipient_phone_number):
            raise ProviderRejectedCall("Retell recipient number must use E.164 format.")

        payload: dict[str, str] = {
            "from_number": self._from_number,
            "to_number": request.recipient_phone_number,
        }
        if self._agent_id:
            payload["override_agent_id"] = self._agent_id
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

        try:
            response = self._client.post(RETELL_CREATE_PHONE_CALL_URL, json=payload, headers=headers)
        except httpx.RequestError:
            raise AmbiguousProviderOutcome(
                "Retell call creation outcome is uncertain; reconciliation is required."
            ) from None

        if response.status_code in {400, 401, 403, 422}:
            if response.status_code in {401, 403}:
                raise ProviderRejectedCall("Retell authentication failed.")
            raise ProviderRejectedCall(f"Retell rejected the call request (HTTP {response.status_code}).")
        if not 200 <= response.status_code < 300:
            # Rate limits and server errors are treated as uncertain until Retell's
            # request-processing guarantees are confirmed; never retry automatically.
            raise AmbiguousProviderOutcome(
                f"Retell call creation returned HTTP {response.status_code}; reconciliation is required."
            )

        try:
            body: Any = response.json()
        except (ValueError, TypeError):
            raise AmbiguousProviderOutcome(
                "Retell returned an unreadable success response; reconciliation is required."
            ) from None

        if not isinstance(body, dict):
            raise AmbiguousProviderOutcome(
                "Retell returned an invalid success response; reconciliation is required."
            )
        call_id = body.get("call_id")
        if not isinstance(call_id, str) or not call_id or call_id != call_id.strip():
            raise AmbiguousProviderOutcome(
                "Retell success response did not contain a valid call_id; reconciliation is required."
            )

        # The verified create response includes these fields. Validate their shape,
        # but do not retain provider payloads or infer any extra behavior from them.
        if any(not isinstance(body.get(field), str) or not body[field] for field in ("agent_id", "call_type")):
            raise AmbiguousProviderOutcome(
                "Retell success response was missing documented call metadata; reconciliation is required."
            )
        try:
            normalized_status = normalize_retell_status(body.get("call_status"))
        except UnknownProviderStatus:
            # A call may already exist even though its status is unrecognized.
            raise AmbiguousProviderOutcome(
                "Retell returned an unsupported call status; reconciliation is required."
            ) from None
        if normalized_status != CallStatus.QUEUED:
            # The verified create-call contract documents `registered` as the
            # initial state. Do not persist an inconsistent local lifecycle state.
            raise AmbiguousProviderOutcome(
                "Retell returned an unexpected initial call status; reconciliation is required."
            )
        return call_id
