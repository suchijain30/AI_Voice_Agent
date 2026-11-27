from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.calls.providers import (
    AmbiguousProviderOutcome,
    ProviderCallRequest,
    ProviderDisabled,
    ProviderRejectedCall,
    UnknownProviderStatus,
)
from app.calls.retell import (
    RETELL_CREATE_PHONE_CALL_URL,
    RetellAdapter,
    normalize_retell_status,
)
from app.calls.types import CallStatus
from app.config import RetellSettings

TEST_API_KEY = "synthetic-retell-contract-key"
TEST_FROM_NUMBER = "+14155550100"
TEST_TO_NUMBER = "+14155550101"


def settings(**overrides):
    values = {
        "retell_calls_enabled": True,
        "retell_api_key": SecretStr(TEST_API_KEY),
        "retell_from_number": TEST_FROM_NUMBER,
        "retell_agent_id": "synthetic-agent-id",
        "_env_file": None,
    }
    values.update(overrides)
    return RetellSettings(**values)


def request(number=TEST_TO_NUMBER):
    return ProviderCallRequest(
        call_id=uuid4(),
        idempotency_key="local-key-not-sent-to-retell",
        recipient_phone_number=number,
        job_title="Synthetic role",
        job_description="Synthetic test context",
    )


def make_adapter(handler, *, configured=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = RetellAdapter.from_settings(configured or settings(), client=client)
    return adapter, client


def valid_response(**overrides):
    return {
        "call_id": "retell-call-test-1",
        "call_status": "registered",
        "agent_id": "synthetic-agent-id",
        "call_type": "phone_call",
    } | overrides


def test_documented_create_contract_maps_call_id_and_bearer_auth():
    observed = {}

    def handler(req):
        observed["url"] = str(req.url)
        observed["auth"] = req.headers.get("Authorization")
        observed["json"] = req.read().decode()
        return httpx.Response(200, json=valid_response())

    adapter, client = make_adapter(handler)
    try:
        provider_id = adapter.start_call(request())
    finally:
        adapter.close()
        client.close()

    assert observed["url"] == RETELL_CREATE_PHONE_CALL_URL
    assert observed["auth"] == f"Bearer {TEST_API_KEY}"
    import json

    assert json.loads(observed["json"]) == {
        "from_number": TEST_FROM_NUMBER,
        "to_number": TEST_TO_NUMBER,
        "override_agent_id": "synthetic-agent-id",
    }
    assert provider_id == "retell-call-test-1"
    assert "idempotency" not in observed["json"]


def test_agent_override_is_omitted_when_not_configured():
    seen = {}
    adapter, client = make_adapter(
        lambda req: (seen.update(json=req.read().decode()) or httpx.Response(200, json=valid_response())),
        configured=settings(retell_agent_id=None),
    )
    try:
        adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    import json

    assert json.loads(seen["json"]) == {"from_number": TEST_FROM_NUMBER, "to_number": TEST_TO_NUMBER}


@pytest.mark.parametrize("call_id", [None, "", 3, " padded "])
def test_missing_or_malformed_call_id_is_ambiguous(call_id):
    adapter, client = make_adapter(lambda _: httpx.Response(200, json=valid_response(call_id=call_id)))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="call_id"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


@pytest.mark.parametrize("status", [None, "", 3, "future_status"])
def test_missing_or_unknown_call_status_is_ambiguous(status):
    adapter, client = make_adapter(lambda _: httpx.Response(200, json=valid_response(call_status=status)))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="status"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


@pytest.mark.parametrize("body", [[], "bad", None])
def test_malformed_success_response_is_ambiguous(body):
    adapter, client = make_adapter(lambda _: httpx.Response(200, json=body))
    try:
        with pytest.raises(AmbiguousProviderOutcome):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


@pytest.mark.parametrize("code", [401, 403])
def test_authentication_errors_are_rejected_without_leaking_key(code):
    adapter, client = make_adapter(lambda _: httpx.Response(code, text=TEST_API_KEY))
    try:
        with pytest.raises(ProviderRejectedCall, match="authentication failed") as error:
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert TEST_API_KEY not in str(error.value)


@pytest.mark.parametrize("code", [400, 422])
def test_validation_errors_are_sanitized_rejections(code):
    adapter, client = make_adapter(lambda _: httpx.Response(code, text=f"secret {TEST_API_KEY}"))
    try:
        with pytest.raises(ProviderRejectedCall, match=f"HTTP {code}") as error:
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert TEST_API_KEY not in str(error.value)


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_rate_limit_and_server_errors_are_ambiguous_and_not_retried(code):
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(code)

    adapter, client = make_adapter(handler)
    try:
        with pytest.raises(AmbiguousProviderOutcome):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert attempts == 1


def test_timeout_is_ambiguous_and_never_retried():
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic timeout")

    adapter, client = make_adapter(handler)
    try:
        with pytest.raises(AmbiguousProviderOutcome) as error:
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert attempts == 1
    assert TEST_API_KEY not in str(error.value)


def test_transport_failure_is_ambiguous():
    adapter, client = make_adapter(lambda _: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    try:
        with pytest.raises(AmbiguousProviderOutcome):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


def test_recipient_must_be_e164_and_is_rejected_before_request():
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json=valid_response())

    adapter, client = make_adapter(handler)
    try:
        with pytest.raises(ProviderRejectedCall, match="E.164"):
            adapter.start_call(request("415-555-0101"))
    finally:
        adapter.close()
        client.close()
    assert attempts == 0


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("registered", CallStatus.QUEUED),
        ("not_connected", CallStatus.NO_ANSWER),
        ("ongoing", CallStatus.IN_PROGRESS),
        ("ended", CallStatus.COMPLETED),
        ("error", CallStatus.FAILED),
    ],
)
def test_documented_status_mapping(status, expected):
    assert normalize_retell_status(status) == expected


def test_unknown_status_normalization_rejected():
    with pytest.raises(UnknownProviderStatus):
        normalize_retell_status("undocumented")


def test_non_initial_status_in_create_response_requires_reconciliation():
    adapter, client = make_adapter(lambda _: httpx.Response(200, json=valid_response(call_status="ongoing")))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="unexpected initial"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


def test_configuration_requires_key_and_e164_from_number_when_enabled():
    with pytest.raises(ValidationError, match="RETELL_API_KEY and RETELL_FROM_NUMBER"):
        RetellSettings(retell_calls_enabled=True, _env_file=None)
    with pytest.raises(ValueError, match="E.164"):
        RetellAdapter(api_key=SecretStr(TEST_API_KEY), from_number="4155550100", enabled=False)
    configured = settings()
    assert TEST_API_KEY not in repr(configured)


def test_disabled_by_default_and_does_not_send_request():
    configured = settings(retell_calls_enabled=False)
    with pytest.raises(ProviderDisabled):
        RetellAdapter.from_settings(configured)

