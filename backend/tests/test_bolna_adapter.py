from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.calls.bolna import BOLNA_CALL_URL, BOLNA_EXECUTION_URL, BolnaAdapter, normalize_bolna_status
from app.calls.providers import (
    AmbiguousProviderOutcome,
    ProviderCallRequest,
    ProviderDisabled,
    ProviderRejectedCall,
    UnknownProviderStatus,
)
from app.calls.types import CallStatus
from app.config import BolnaSettings

TEST_API_KEY = "synthetic-contract-test-key"


def configured_settings(**overrides):
    values = {
        "database_url": "sqlite://",
        "bolna_calls_enabled": True,
        "bolna_api_key": SecretStr(TEST_API_KEY),
        "bolna_agent_id": "synthetic-agent-id",
        "_env_file": None,
    }
    values.update(overrides)
    return BolnaSettings(**values)


def request():
    return ProviderCallRequest(
        call_id=uuid4(),
        idempotency_key="local-idempotency-key-not-sent-to-provider",
        recipient_phone_number="TEST-RECIPIENT",
        job_title="Synthetic role",
        job_description="Synthetic contract test context",
    )


def run_adapter(handler, *, settings=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = BolnaAdapter.from_settings(settings or configured_settings(), client=client)
    return adapter, client


def test_documented_success_request_response_and_bearer_header():
    seen = {}

    def handler(http_request):
        seen["url"] = str(http_request.url)
        seen["headers"] = http_request.headers
        seen["json"] = http_request.read().decode()
        return httpx.Response(200, json={"execution_id": "123e4567-e89b-42d3-a456-426614174000", "status": "queued"})

    adapter, client = run_adapter(handler)
    try:
        execution_id = adapter.start_call(request())
    finally:
        adapter.close()
        client.close()

    assert seen["url"] == BOLNA_CALL_URL
    assert seen["headers"]["Authorization"] == f"Bearer {TEST_API_KEY}"
    assert httpx.Headers(seen["headers"])["Content-Type"] == "application/json"
    import json

    body = json.loads(seen["json"])
    assert body == {
        "agent_id": "synthetic-agent-id",
        "recipient_phone_number": "TEST-RECIPIENT",
    }
    assert execution_id == "123e4567-e89b-42d3-a456-426614174000"
    assert "idempotency" not in seen["json"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"execution_id": ""},
        {"execution_id": "execution-test-123"},
        {"execution_id": " execution-with-surrounding-whitespace "},
        {"execution_id": 123},
        ["not", "an", "object"],
    ],
)
def test_missing_or_malformed_execution_identifier_is_ambiguous(body):
    adapter, client = run_adapter(lambda _: httpx.Response(200, json=body))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="execution_id"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


def test_malformed_json_success_response_is_ambiguous():
    adapter, client = run_adapter(lambda _: httpx.Response(200, content=b"not-json"))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="unreadable"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


def test_valid_execution_identifier_without_documented_status_is_ambiguous():
    adapter, client = run_adapter(lambda _: httpx.Response(200, json={
        "execution_id": "123e4567-e89b-42d3-a456-426614174000"
    }))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="status"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


def test_unexpected_creation_status_is_ambiguous():
    adapter, client = run_adapter(lambda _: httpx.Response(200, json={
        "execution_id": "123e4567-e89b-42d3-a456-426614174000", "status": "completed"
    }))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="unexpected creation status"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


@pytest.mark.parametrize("status_code", [401])
def test_authentication_failures_are_safe_and_do_not_expose_key(status_code):
    adapter, client = run_adapter(
        lambda _: httpx.Response(status_code, text=f"echo {TEST_API_KEY}")
    )
    try:
        with pytest.raises(ProviderRejectedCall, match="authentication failed") as error:
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert TEST_API_KEY not in str(error.value)


@pytest.mark.parametrize("status_code", [400, 422])
def test_validation_failures_are_definitive_and_sanitized(status_code):
    adapter, client = run_adapter(
        lambda _: httpx.Response(status_code, text=f"invalid request; key={TEST_API_KEY}")
    )
    try:
        with pytest.raises(ProviderRejectedCall, match=f"HTTP {status_code}") as error:
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert TEST_API_KEY not in str(error.value)


def test_undocumented_forbidden_response_is_ambiguous():
    adapter, client = run_adapter(lambda _: httpx.Response(403, text="forbidden"))
    try:
        with pytest.raises(AmbiguousProviderOutcome):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_server_errors_are_ambiguous_and_never_retried(status_code):
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, text="server error")

    adapter, client = run_adapter(handler)
    try:
        with pytest.raises(AmbiguousProviderOutcome):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert attempts == 1


def test_undocumented_http_status_is_ambiguous():
    adapter, client = run_adapter(lambda _: httpx.Response(429, text="rate limited"))
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="HTTP 429"):
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()


def test_timeout_is_ambiguous_and_never_retried():
    attempts = 0

    def handler(_):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic timeout")

    adapter, client = run_adapter(handler)
    try:
        with pytest.raises(AmbiguousProviderOutcome, match="uncertain") as error:
            adapter.start_call(request())
    finally:
        adapter.close()
        client.close()
    assert attempts == 1
    assert TEST_API_KEY not in str(error.value)


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [
        ("queued", CallStatus.QUEUED),
        ("ringing", CallStatus.RINGING),
        ("in-progress", CallStatus.IN_PROGRESS),
        ("call-disconnected", CallStatus.FINALIZING),
        ("completed", CallStatus.COMPLETED),
        ("no-answer", CallStatus.NO_ANSWER),
        ("busy", CallStatus.BUSY),
        ("failed", CallStatus.FAILED),
        ("stopped", CallStatus.CANCELED),
        ("error", CallStatus.FAILED),
        ("balance-low", CallStatus.FAILED),
    ],
)
def test_documented_status_normalization(provider_status, expected):
    assert normalize_bolna_status(provider_status) == expected


@pytest.mark.parametrize("provider_status", ["Completed", "unknown", ""])
def test_unknown_or_undocumented_status_is_rejected(provider_status):
    with pytest.raises(UnknownProviderStatus):
        normalize_bolna_status(provider_status)


def test_bolna_configuration_is_validated_and_secret_is_redacted():
    with pytest.raises(ValidationError) as error:
        BolnaSettings(bolna_calls_enabled=True, _env_file=None)
    assert "BOLNA_API_KEY and BOLNA_AGENT_ID are required" in str(error.value)

    settings = configured_settings()
    assert TEST_API_KEY not in repr(settings)


def test_recruitment_configuration_is_mapped_to_user_data_without_phone_or_email():
    from app.recruitment_agent.schemas import RecruitmentAgentConfiguration

    configuration = RecruitmentAgentConfiguration.model_validate(
        {
            "candidate": {
                "application_id": str(uuid4()),
                "name": "Synthetic Candidate",
                "phone_number": "+919999999999",
                "email": "private@example.test",
                "stated_experience_years": 4,
                "skills": ["Python"],
                "location": "Pune",
            },
            "job": {"title": "Engineer", "description": "Synthetic role", "candidate_listed_skills": ["Python"]},
            "screening": {
                "session_id": str(uuid4()),
                "questions": [{
                    "question_key": "experience_years", "question_text": "How much experience?",
                    "required": True, "order": 1, "category": "experience",
                    "follow_up_guidance": "Clarify role relevance.",
                }],
            },
        }
    )
    from app.calls.bolna import bolna_user_data
    values = bolna_user_data(configuration)
    assert values["candidate_name"] == "Synthetic Candidate"
    assert "experience_years" in values["screening_questions"]
    assert "Clarify role relevance" in values["screening_questions"]
    assert "+919999999999" not in str(values)
    assert "private@example.test" not in str(values)


def test_start_call_includes_only_documented_context_container_and_omits_retry_config():
    import json
    seen = {}
    def handler(http_request):
        seen["payload"] = json.loads(http_request.read())
        return httpx.Response(200, json={"execution_id": "123e4567-e89b-42d3-a456-426614174000", "status": "queued"})
    from app.recruitment_agent.schemas import RecruitmentAgentConfiguration
    configuration = RecruitmentAgentConfiguration.model_validate({
        "candidate": {"application_id": str(uuid4()), "name": "Synthetic Candidate"},
        "job": {"title": "Engineer", "description": "Synthetic role"},
        "screening": {"session_id": str(uuid4()), "questions": [{
            "question_key": "notice_period", "question_text": "What is your notice period?",
            "required": True, "order": 1, "category": "availability",
        }]},
    })
    original = request()
    enriched = ProviderCallRequest(**(original.__dict__ | {"agent_configuration": configuration}))
    adapter, client = run_adapter(handler)
    try:
        adapter.start_call(enriched)
    finally:
        adapter.close(); client.close()
    assert set(seen["payload"]) == {"agent_id", "recipient_phone_number", "user_data"}
    assert "retry_config" not in seen["payload"]
    assert "notice_period" in seen["payload"]["user_data"]["screening_questions"]


def test_execution_retrieval_parses_allowlisted_results_and_bearer_auth():
    seen = {}
    def handler(http_request):
        seen["url"] = str(http_request.url)
        seen["authorization"] = http_request.headers["Authorization"]
        return httpx.Response(200, json={
            "status": "completed", "transcript": "Synthetic transcript",
            "extracted_data": {"notice_period": "30 days"}, "duration": 90,
            "recording_url": "https://not-retained.invalid/audio",
        })
    adapter, client = run_adapter(handler)
    try:
        execution = adapter.get_execution("123e4567-e89b-42d3-a456-426614174000")
    finally:
        adapter.close(); client.close()
    assert seen["url"] == BOLNA_EXECUTION_URL.format("123e4567-e89b-42d3-a456-426614174000")
    assert seen["authorization"] == f"Bearer {TEST_API_KEY}"
    assert execution.transcript == "Synthetic transcript"
    assert execution.duration == 90
    assert not hasattr(execution, "recording_url")


@pytest.mark.parametrize("body", [{}, {"status": "future-status"}, {"status": "completed", "duration": -2}, ["bad"]])
def test_execution_retrieval_rejects_invalid_or_unknown_response(body):
    from app.calls.providers import ProviderRetrievalError
    adapter, client = run_adapter(lambda _: httpx.Response(200, json=body))
    try:
        with pytest.raises(ProviderRetrievalError):
            adapter.get_execution("123e4567-e89b-42d3-a456-426614174000")
    finally:
        adapter.close(); client.close()


def test_execution_retrieval_failure_is_sanitized_and_does_not_retry():
    from app.calls.providers import ProviderRetrievalError
    requests = []
    def handler(_):
        requests.append(1)
        raise httpx.ReadTimeout(TEST_API_KEY)
    adapter, client = run_adapter(handler)
    try:
        with pytest.raises(ProviderRetrievalError) as error:
            adapter.get_execution("123e4567-e89b-42d3-a456-426614174000")
    finally:
        adapter.close(); client.close()
    assert requests == [1]
    assert TEST_API_KEY not in str(error.value)


def test_bolna_adapter_is_disabled_unless_explicitly_enabled():
    settings = configured_settings(bolna_calls_enabled=False)
    adapter = BolnaAdapter(
        api_key=settings.bolna_api_key,
        agent_id=settings.bolna_agent_id,
        enabled=False,
        client=httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected HTTP request"))),
    )
    try:
        with pytest.raises(ProviderDisabled):
            adapter.start_call(request())
    finally:
        adapter.close()
