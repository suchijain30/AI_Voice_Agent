from typing import Protocol
from uuid import uuid4

from app.calls.types import ProviderCallRequest


class ProviderError(Exception):
    """Base for sanitized provider operation failures."""


class ProviderRejectedCall(ProviderError):
    """The provider returned a response that definitively rejected the request."""


class AmbiguousProviderOutcome(ProviderError):
    """The provider may have accepted the call request; reconcile before another attempt."""


class ProviderDisabled(ProviderError):
    """A provider adapter is disabled by local configuration."""


class UnknownProviderStatus(ProviderError):
    """The provider returned a status without a verified normalized mapping."""


class ProviderRetrievalError(ProviderError):
    """A provider execution could not be retrieved safely."""


class CallProvider(Protocol):
    """Narrow provider boundary used by the lifecycle service."""

    name: str

    def start_call(self, request: ProviderCallRequest) -> str:
        """Return the provider's call identifier."""


class MockProvider:
    """Local-only provider. It creates identifiers and never makes network calls."""

    name = "mock"

    def start_call(self, request: ProviderCallRequest) -> str:
        del request
        return f"mock-{uuid4()}"
