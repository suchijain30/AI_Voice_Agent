from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app.calls.bolna import BolnaAdapter
from app.calls.bolna_routes import get_enabled_bolna_adapter
from app.calls.bolna_sync import BolnaSyncService, BolnaWebhookAuthenticationError
from app.calls.providers import ProviderDisabled
from app.calls.types import CallStatus
from app.config import BolnaSettings
from app.models import Call, ScreeningSession
from app.calls.bolna_sync import BolnaSyncService

EXECUTION_ID = "123e4567-e89b-42d3-a456-426614174000"


def _candidate(client):
    response = client.post("/api/candidates", json={
        "full_name": "Synthetic Candidate", "phone_number": "+91 98765 43210",
        "job_title": "Test Engineer", "job_description": "Synthetic integration-test role.",
        "skills": ["Python", "Testing"],
    })
    assert response.status_code == 201
    return response.json()


def test_bolna_screening_call_replay_sync_and_result_persistence(client):
    candidate = _candidate(client)
    session_response = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"]})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]
    queued = {"execution_id": EXECUTION_ID, "status": "queued"}
    executions = [
        {"status": "call-disconnected"},
        {"status": "completed", "transcript": "Synthetic response.",
         "summary": "Synthetic summary.", "extracted_data": {"notice_period": "30 days"}, "duration": 75},
    ]
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=queued if request.method == "POST" else executions.pop(0))

    http = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = BolnaAdapter(api_key=SecretStr("offline-secret"), agent_id="agent-test", enabled=True, client=http)
    previous = client.app.dependency_overrides.get(get_enabled_bolna_adapter)
    client.app.dependency_overrides[get_enabled_bolna_adapter] = lambda: adapter
    try:
        created = client.post(f"/api/screening-sessions/{session_id}/bolna-call")
        assert created.status_code == 201
        call_id = created.json()["id"]
        import json
        payload = json.loads(requests[0].content)
        assert payload["user_data"]["candidate_name"] == "Synthetic Candidate"
        assert "screening_questions" in payload["user_data"]
        assert "retry_config" not in payload
        assert candidate["phone_number"] not in str(payload["user_data"])

        replay = client.post(f"/api/screening-sessions/{session_id}/bolna-call")
        assert replay.status_code == 200
        assert replay.json()["id"] == call_id
        assert len([request for request in requests if request.method == "POST"]) == 1

        interim = client.post(f"/api/calls/{call_id}/bolna-sync")
        assert interim.status_code == 200
        assert interim.json()["call"]["status"] == CallStatus.FINALIZING.value
        assert not interim.json()["result_available"]
        completed = client.post(f"/api/calls/{call_id}/bolna-sync")
        assert completed.status_code == 200
        assert completed.json()["call"]["status"] == CallStatus.COMPLETED.value
        assert completed.json()["result_available"]

        second_session = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"]})
        assert second_session.status_code == 201
        second_call = client.post(
            f"/api/screening-sessions/{second_session.json()['id']}/bolna-call"
        )
        assert second_call.status_code == 409
        assert "already exists for this candidate application" in second_call.json()["detail"]
        assert len([request for request in requests if request.method == "POST"]) == 1

    finally:
        adapter.close()
        http.close()
        if previous is None:
            client.app.dependency_overrides.pop(get_enabled_bolna_adapter, None)
        else:
            client.app.dependency_overrides[get_enabled_bolna_adapter] = previous

    db = sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)()
    try:
        screening = db.get(ScreeningSession, UUID(session_id))
        call = db.get(Call, UUID(call_id))
        assert screening.call_id == call.id
        assert screening.provider_transcript == "Synthetic response."
        assert screening.provider_summary == "Synthetic summary."
        assert screening.provider_extracted_data == {"notice_period": "30 days"}
        assert screening.provider_call_duration_seconds == 75
    finally:
        db.close()


def test_disabled_bolna_configuration_rejects_adapter_activation():
    with pytest.raises(ProviderDisabled):
        BolnaAdapter.from_settings(BolnaSettings(bolna_calls_enabled=False, _env_file=None))


def test_bolna_call_route_is_disabled_without_explicit_configuration(client, monkeypatch):
    candidate = _candidate(client)
    session_response = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"]})
    monkeypatch.setenv("BOLNA_CALLS_ENABLED", "false")
    response = client.post(f"/api/screening-sessions/{session_response.json()['id']}/bolna-call")
    assert response.status_code == 503
    assert response.json()["detail"] == "Bolna integration is disabled by configuration."


def test_stale_finalizing_worklist_uses_updated_at_and_makes_no_provider_request(client):
    from app.calls.providers import MockProvider
    from app.calls.service import CallLifecycleService

    candidate = _candidate(client)
    now = datetime.now(timezone.utc)
    with sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)() as db:
        candidate_id = UUID(candidate["id"])
        db_call, created = CallLifecycleService(db, MockProvider(), enabled=True).create_call(
            candidate_id, "stale-finalizing-fixture"
        )
        assert created
        db_call.provider = "bolna"
        db_call.provider_call_id = EXECUTION_ID
        db_call.status = CallStatus.FINALIZING.value
        db_call.updated_at = now - timedelta(minutes=30)
        db.commit()

    with sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)() as db:
        stale = BolnaSyncService.list_stale_finalizing_calls(
            db, stale_after_seconds=900, now=now, limit=10
        )
        assert [call.provider_call_id for call in stale] == [EXECUTION_ID]
        fresh = BolnaSyncService.list_stale_finalizing_calls(
            db, stale_after_seconds=3600, now=now, limit=10
        )
        assert fresh == []


def test_failed_or_unknown_execution_retrieval_preserves_finalizing_and_never_creates_call(client):
    from app.calls.providers import MockProvider
    from app.calls.service import CallLifecycleService

    candidate = _candidate(client)
    call_id = None
    with sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)() as db:
        call, _ = CallLifecycleService(db, MockProvider(), enabled=True).create_call(
            UUID(candidate["id"]), "sync-failure-fixture"
        )
        call.provider = "bolna"
        call.provider_call_id = EXECUTION_ID
        call.status = CallStatus.FINALIZING.value
        call_id = call.id
        db.commit()

    methods = []
    responses = [
        httpx.Response(503, text="temporary failure"),
        httpx.Response(200, json={"status": "unrecognized-provider-status"}),
    ]
    def handler(request):
        methods.append(request.method)
        return responses.pop(0)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = BolnaAdapter(api_key=SecretStr("offline-secret"), agent_id="agent-test", enabled=True, client=http)
    previous = client.app.dependency_overrides.get(get_enabled_bolna_adapter)
    client.app.dependency_overrides[get_enabled_bolna_adapter] = lambda: adapter
    try:
        for _ in range(2):
            response = client.post(f"/api/calls/{call_id}/bolna-sync")
            assert response.status_code == 409
        assert methods == ["GET", "GET"]
    finally:
        adapter.close()
        http.close()
        if previous is None:
            client.app.dependency_overrides.pop(get_enabled_bolna_adapter, None)
        else:
            client.app.dependency_overrides[get_enabled_bolna_adapter] = previous

    with sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)() as db:
        assert db.get(Call, call_id).status == CallStatus.FINALIZING.value


def test_ambiguous_start_is_not_resubmitted_for_same_screening_session(client):
    candidate = _candidate(client)
    session_response = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"]})
    session_id = session_response.json()["id"]
    attempts = []

    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout("synthetic timeout")

    http = httpx.Client(transport=httpx.MockTransport(timeout))
    adapter = BolnaAdapter(api_key=SecretStr("offline-secret"), agent_id="agent-test", enabled=True, client=http)
    previous = client.app.dependency_overrides.get(get_enabled_bolna_adapter)
    client.app.dependency_overrides[get_enabled_bolna_adapter] = lambda: adapter
    try:
        first = client.post(f"/api/screening-sessions/{session_id}/bolna-call")
        replay = client.post(f"/api/screening-sessions/{session_id}/bolna-call")
        assert first.status_code == 503
        assert "reconciliation is required" in first.json()["detail"]
        assert replay.status_code == 200
        assert replay.json()["status"] == CallStatus.RECONCILIATION_REQUIRED.value
        assert len(attempts) == 1
    finally:
        adapter.close()
        http.close()
        if previous is None:
            client.app.dependency_overrides.pop(get_enabled_bolna_adapter, None)
        else:
            client.app.dependency_overrides[get_enabled_bolna_adapter] = previous


def test_webhook_processor_requires_secret_and_deduplicates_without_http(client):
    from app.models import Candidate

    candidate = _candidate(client)
    session_response = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"]})
    session_id = UUID(session_response.json()["id"])
    db_factory = sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)
    with db_factory() as db:
        candidate_row = db.get(Candidate, UUID(candidate["id"]))
        call = Call(
            candidate_id=candidate_row.id, provider="bolna", provider_call_id=EXECUTION_ID,
            idempotency_key="webhook-test-call", status=CallStatus.QUEUED.value,
        )
        db.add(call)
        db.flush()
        db.get(ScreeningSession, session_id).call_id = call.id
        db.commit()
        call_id = call.id

    settings = BolnaSettings(bolna_webhook_secret=SecretStr("expected-test-header"), _env_file=None)
    http = httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Webhook path must not make HTTP requests")))
    adapter = BolnaAdapter(api_key=SecretStr("offline-secret"), agent_id="agent-test", enabled=True, client=http)
    payload = {"execution_id": EXECUTION_ID, "status": "call-disconnected"}
    try:
        with db_factory() as db:
            processor = BolnaSyncService(db, adapter)
            with pytest.raises(BolnaWebhookAuthenticationError):
                processor.process_webhook(payload, settings=settings, supplied_secret="wrong")
        with db_factory() as db:
            processor = BolnaSyncService(db, adapter)
            _, duplicate = processor.process_webhook(
                payload, settings=settings, supplied_secret="expected-test-header"
            )
            assert duplicate is False
        with db_factory() as db:
            processor = BolnaSyncService(db, adapter)
            call, duplicate = processor.process_webhook(
                payload, settings=settings, supplied_secret="expected-test-header"
            )
            assert duplicate is True
            assert call.id == call_id
            assert call.status == CallStatus.FINALIZING.value
    finally:
        adapter.close()
        http.close()
