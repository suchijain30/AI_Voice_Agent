from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.calls.providers import MockProvider
from app.calls.routes import get_call_service
from app.calls.service import (
    CallExecutionDisabled,
    CallLifecycleService,
    CallNotFound,
    CandidateNotFound,
    IdempotencyConflict,
    InvalidCallTransition,
    ProviderEventConflict,
    ProviderOperationError,
    UnresolvedCallOutcome,
)
from app.calls.types import CallStatus, NormalizedProviderEvent
from app.calls.providers import AmbiguousProviderOutcome, ProviderRejectedCall
from app.calls.retell import RetellAdapter
from pydantic import SecretStr
import httpx
from app.database import get_db
from app.main import app
from app.models import Call, CallEvent
import app.main as main_module


def candidate_payload():
    return {
        "full_name": "Test Candidate",
        "phone_number": "+91 98765 43210",
        "job_title": "Test Engineer",
        "job_description": "Synthetic test role for local mock lifecycle tests.",
        "skills": ["Testing"],
    }


@pytest.fixture
def enabled_mock_client(client):
    previous = app.dependency_overrides.get(get_call_service)

    def enabled_service(db: Session = Depends(get_db)):
        return CallLifecycleService(db, MockProvider(), enabled=True)

    app.dependency_overrides[get_call_service] = enabled_service
    yield client
    if previous is None:
        app.dependency_overrides.pop(get_call_service, None)
    else:
        app.dependency_overrides[get_call_service] = previous


def create_candidate(client):
    response = client.post("/api/candidates", json=candidate_payload())
    assert response.status_code == 201
    return response.json()


def create_mock_call(client, candidate_id, key="mock-key-1"):
    return client.post(
        f"/api/candidates/{candidate_id}/calls",
        headers={"Idempotency-Key": key},
    )


def service_for_test_db():
    test_session_factory = sessionmaker(bind=main_module.engine, autoflush=False, expire_on_commit=False)
    return test_session_factory


def test_mock_call_creation_and_read(enabled_mock_client):
    candidate = create_candidate(enabled_mock_client)
    response = create_mock_call(enabled_mock_client, candidate["id"])

    assert response.status_code == 201
    call = response.json()
    assert call["candidate_id"] == candidate["id"]
    assert call["provider"] == "mock"
    assert call["provider_call_id"].startswith("mock-")
    assert call["status"] == CallStatus.QUEUED.value

    fetched = enabled_mock_client.get(f"/api/calls/{call['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == call["id"]


def test_mock_call_execution_is_disabled_by_default(client):
    candidate = create_candidate(client)
    response = create_mock_call(client, candidate["id"])
    assert response.status_code == 503
    assert response.json()["detail"] == "Mock call execution is disabled."


def test_call_idempotency_returns_existing_record(enabled_mock_client):
    candidate = create_candidate(enabled_mock_client)
    first = create_mock_call(enabled_mock_client, candidate["id"], "same-key")
    replay = create_mock_call(enabled_mock_client, candidate["id"], "same-key")

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    with service_for_test_db()() as db:
        assert db.scalar(select(func.count(Call.id))) == 1


def test_idempotency_key_cannot_be_reused_for_another_candidate(enabled_mock_client):
    first_candidate = create_candidate(enabled_mock_client)
    first = create_mock_call(enabled_mock_client, first_candidate["id"], "shared-key")
    second_candidate = enabled_mock_client.post(
        "/api/candidates", json=candidate_payload() | {"phone_number": "+91 91234 56780"}
    ).json()

    response = create_mock_call(enabled_mock_client, second_candidate["id"], "shared-key")
    assert first.status_code == 201
    assert response.status_code == 409


def test_call_creation_requires_an_existing_candidate(enabled_mock_client):
    response = create_mock_call(enabled_mock_client, str(uuid4()))
    assert response.status_code == 404


def test_provider_error_marks_call_failed_and_does_not_retry(enabled_mock_client):
    candidate_json = create_candidate(enabled_mock_client)

    class FailingProvider:
        name = "mock-failure"
        attempts = 0

        def start_call(self, request):
            self.attempts += 1
            raise ProviderRejectedCall("simulated local mock rejection")

    provider = FailingProvider()
    with service_for_test_db()() as db:
        service = CallLifecycleService(db, provider, enabled=True)
        with pytest.raises(ProviderOperationError):
            service.create_call(UUID(candidate_json["id"]), "failed-key")
        saved = db.scalar(select(Call).where(Call.idempotency_key == "failed-key"))

    assert provider.attempts == 1
    assert saved.status == CallStatus.FAILED.value


def test_ambiguous_creation_blocks_same_candidate_provider_even_with_new_key(enabled_mock_client):
    candidate_json = create_candidate(enabled_mock_client)

    class TimeoutProvider:
        name = "mock-timeout"
        attempts = 0

        def start_call(self, request):
            self.attempts += 1
            raise AmbiguousProviderOutcome("simulated timeout")

    provider = TimeoutProvider()
    with service_for_test_db()() as db:
        service = CallLifecycleService(db, provider, enabled=True)
        candidate_id = UUID(candidate_json["id"])
        with pytest.raises(ProviderOperationError, match="reconciliation is required"):
            service.create_call(candidate_id, "ambiguous-key")
        saved = db.scalar(select(Call).where(Call.idempotency_key == "ambiguous-key"))
        assert saved.status == CallStatus.RECONCILIATION_REQUIRED.value
        assert saved.provider_outcome == "ambiguous"

        with pytest.raises(UnresolvedCallOutcome):
            service.create_call(candidate_id, "different-key")
        replay, created = service.create_call(candidate_id, "ambiguous-key")
        assert created is False
        assert replay.status == CallStatus.RECONCILIATION_REQUIRED.value

    assert provider.attempts == 1


def test_retell_timeout_cannot_be_resubmitted_with_a_new_local_key(enabled_mock_client):
    candidate_json = create_candidate(enabled_mock_client)
    attempts = 0

    def timeout(_):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic timeout")

    client = httpx.Client(transport=httpx.MockTransport(timeout))
    provider = RetellAdapter(
        api_key=SecretStr("synthetic-retell-key"),
        from_number="+14155550100",
        enabled=True,
        client=client,
    )
    try:
        with service_for_test_db()() as db:
            service = CallLifecycleService(db, provider, enabled=True)
            candidate_id = UUID(candidate_json["id"])
            with pytest.raises(ProviderOperationError, match="reconciliation is required"):
                service.create_call(candidate_id, "retell-timeout-key")
            saved = db.scalar(select(Call).where(Call.idempotency_key == "retell-timeout-key"))
            assert saved.provider == "retell"
            assert saved.status == CallStatus.RECONCILIATION_REQUIRED.value
            with pytest.raises(UnresolvedCallOutcome):
                service.create_call(candidate_id, "retell-new-key")
    finally:
        provider.close()
        client.close()
    assert attempts == 1


def test_explicit_reconciliation_never_calls_provider(enabled_mock_client):
    candidate_json = create_candidate(enabled_mock_client)

    class TimeoutProvider:
        name = "mock-timeout"
        attempts = 0

        def start_call(self, request):
            self.attempts += 1
            raise AmbiguousProviderOutcome("simulated timeout")

    provider = TimeoutProvider()
    with service_for_test_db()() as db:
        service = CallLifecycleService(db, provider, enabled=True)
        candidate_id = UUID(candidate_json["id"])
        with pytest.raises(ProviderOperationError):
            service.create_call(candidate_id, "reconcile-key")
        call = db.scalar(select(Call).where(Call.idempotency_key == "reconcile-key"))
        resolved = service.reconcile_ambiguous_call(call.id, provider_call_id=None)
        assert resolved.status == CallStatus.FAILED.value
        assert resolved.provider_outcome == "reconciled_not_created"

    assert provider.attempts == 1


def create_call_in_service(client):
    candidate_json = create_candidate(client)
    response = create_mock_call(client, candidate_json["id"])
    assert response.status_code == 201
    return response.json()


def apply_event(call_json, provider_event_id, status):
    with service_for_test_db()() as db:
        service = CallLifecycleService(db, MockProvider(), enabled=True)
        return service.handle_event(
            NormalizedProviderEvent(
                provider="mock",
                provider_call_id=call_json["provider_call_id"],
                provider_event_id=provider_event_id,
                event_type=f"call.{status.value}",
                status=status,
                occurred_at=datetime.now(timezone.utc),
            )
        )


def test_valid_call_state_transitions_and_timestamps(enabled_mock_client):
    call = create_call_in_service(enabled_mock_client)
    for event_id, status in (
        ("event-1", CallStatus.INITIATED),
        ("event-2", CallStatus.RINGING),
        ("event-3", CallStatus.IN_PROGRESS),
        ("event-4", CallStatus.COMPLETED),
    ):
        result = apply_event(call, event_id, status)
        assert result.status == status
        assert result.duplicate is False

    with service_for_test_db()() as db:
        saved = db.get(Call, UUID(call["id"]))
        assert saved.status == CallStatus.COMPLETED.value
        assert saved.started_at is not None
        assert saved.ended_at is not None
        assert db.scalar(select(func.count(CallEvent.id))) == 4


def test_duplicate_event_is_idempotent(enabled_mock_client):
    call = create_call_in_service(enabled_mock_client)
    first = apply_event(call, "event-duplicate", CallStatus.INITIATED)
    replay = apply_event(call, "event-duplicate", CallStatus.INITIATED)

    assert first.duplicate is False
    assert replay.duplicate is True
    with service_for_test_db()() as db:
        assert db.scalar(select(func.count(CallEvent.id))) == 1


def test_invalid_transition_does_not_update_call_or_record_event(enabled_mock_client):
    call = create_call_in_service(enabled_mock_client)
    with service_for_test_db()() as db:
        service = CallLifecycleService(db, MockProvider(), enabled=True)
        event = NormalizedProviderEvent(
            provider="mock",
            provider_call_id=call["provider_call_id"],
            provider_event_id="invalid-transition",
            event_type="call.completed",
            status=CallStatus.COMPLETED,
        )
        with pytest.raises(InvalidCallTransition):
            service.handle_event(event)

    with service_for_test_db()() as db:
        saved = db.get(Call, UUID(call["id"]))
        assert saved.status == CallStatus.QUEUED.value
        assert db.scalar(select(func.count(CallEvent.id))) == 0


def test_unknown_call_and_wrong_provider_events_are_rejected(enabled_mock_client):
    create_call_in_service(enabled_mock_client)
    with service_for_test_db()() as db:
        service = CallLifecycleService(db, MockProvider(), enabled=True)
        with pytest.raises(CallNotFound):
            service.get_call(uuid4())
        with pytest.raises(CallNotFound):
            service.handle_event(
                NormalizedProviderEvent(
                    provider="mock",
                    provider_call_id="unknown-call",
                    provider_event_id="unknown-event",
                    event_type="call.initiated",
                    status=CallStatus.INITIATED,
                )
            )
        with pytest.raises(ProviderEventConflict):
            service.handle_event(
                NormalizedProviderEvent(
                    provider="retell",
                    provider_call_id="unknown-call",
                    provider_event_id="wrong-provider-event",
                    event_type="call.initiated",
                    status=CallStatus.INITIATED,
                )
            )


def test_candidate_not_found_and_disabled_service_errors(client):
    with service_for_test_db()() as db:
        with pytest.raises(CallExecutionDisabled):
            CallLifecycleService(db, MockProvider()).create_call(uuid4(), "disabled-key")
        with pytest.raises(CandidateNotFound):
            CallLifecycleService(db, MockProvider(), enabled=True).create_call(uuid4(), "missing-key")


def test_migration_revision_uses_existing_duplicate_apps_revision():
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    revision = ScriptDirectory.from_config(config).get_revision("0003_call_lifecycle")
    assert revision.down_revision == "0002_duplicate_apps"
    assert revision.revision == "0003_call_lifecycle"

    outcomes_revision = ScriptDirectory.from_config(config).get_revision("0004_call_outcomes")
    assert outcomes_revision.down_revision == "0003_call_lifecycle"

    screening_revision = ScriptDirectory.from_config(config).get_revision("0005_screening_workflow")
    assert screening_revision.down_revision == "0004_call_outcomes"

    conversations_revision = ScriptDirectory.from_config(config).get_revision("0006_screening_conversations")
    assert conversations_revision.down_revision == "0005_screening_workflow"

    bolna_revision = ScriptDirectory.from_config(config).get_revision("0007_bolna_finalization")
    assert bolna_revision.down_revision == "0006_screening_conversations"
