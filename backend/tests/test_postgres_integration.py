import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from threading import Lock
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, make_url, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from pydantic import SecretStr

from app.database import get_db
from app.main import app
import app.main as main_module
from app.calls.bolna import BolnaAdapter
from app.calls.bolna_routes import get_enabled_bolna_adapter
from app.calls.types import CallStatus
from app.models import Call, Candidate, ScreeningSession


EXPECTED_TEST_DATABASE = "hr_voice_poc_test"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.postgres
def test_postgres_migrations_and_concurrent_duplicate_protection(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL explicitly to run the PostgreSQL integration test.")

    url = make_url(database_url)
    if (
        not url.drivername.startswith("postgresql")
        or url.database != EXPECTED_TEST_DATABASE
        or url.host not in {"localhost", "127.0.0.1", "::1"}
    ):
        pytest.fail(
            "PostgreSQL integration tests require a local database named hr_voice_poc_test. "
            "The existing hr_voice_poc database is never accepted."
        )

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        actual_database = connection.scalar(text("SELECT current_database()"))
        if actual_database != EXPECTED_TEST_DATABASE:
            engine.dispose()
            pytest.fail("Connected database name did not match the dedicated test database.")
        existing_tables = list(connection.scalars(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )))
        if existing_tables:
            engine.dispose()
            pytest.fail(
                "The dedicated PostgreSQL test database must be empty before this test. "
                "No schema changes were made."
            )

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    monkeypatch.setenv("DATABASE_URL", database_url)
    migration_attempted = False
    previous_engine = main_module.engine
    previous_override = app.dependency_overrides.get(get_db)

    def override_db():
        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as session:
            yield session

    try:
        migration_attempted = True

        # Seed duplicate Bolna calls at the prior migration head and confirm
        # 0007 preflight aborts without changing any rows or schema.
        command.upgrade(alembic_config, "0006_screening_conversations")
        seed_candidate_id = uuid4()
        duplicate_call_ids = [uuid4(), uuid4()]
        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
            db.add(Candidate(
                id=seed_candidate_id,
                full_name="Synthetic Migration Preflight",
                phone_number="+91 90000 10001",
                normalized_phone_number="+919000010001",
                job_title="Migration Preflight Role",
                normalized_job_title="migration preflight role",
                job_description="Synthetic test-only row.",
                skills=[],
            ))
            db.add_all([
                Call(
                    id=call_id, candidate_id=seed_candidate_id, provider="bolna",
                    idempotency_key=f"preflight-{index}", status=CallStatus.QUEUED.value,
                )
                for index, call_id in enumerate(duplicate_call_ids)
            ])
            db.commit()

        with pytest.raises(RuntimeError, match="multiple Bolna calls already exist") as preflight_error:
            command.upgrade(alembic_config, "head")
        assert str(seed_candidate_id) in str(preflight_error.value)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0006_screening_conversations"
            assert connection.scalar(text("SELECT count(*) FROM calls WHERE candidate_id = :id"), {"id": seed_candidate_id}) == 2
            columns = set(connection.scalars(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'screening_sessions'"
            )))
            assert "provider_transcript" not in columns
            assert "provider_summary" not in columns

        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
            db.query(Call).filter(Call.id.in_(duplicate_call_ids)).delete(synchronize_session=False)
            db.query(Candidate).filter(Candidate.id == seed_candidate_id).delete(synchronize_session=False)
            db.commit()

        command.upgrade(alembic_config, "head")
        app.dependency_overrides[get_db] = override_db
        main_module.engine = engine

        # Verify 0007's result columns, status check and partial unique index.
        with engine.connect() as connection:
            columns = set(connection.scalars(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'screening_sessions'"
            )))
            assert {
                "provider_transcript", "provider_summary", "provider_extracted_data",
                "provider_call_duration_seconds",
            } <= columns
            call_check = connection.scalar(text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_calls_status'"
            ))
            assert "finalizing" in call_check
            index_definition = connection.scalar(text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_calls_one_bolna_per_candidate'"
            ))
            assert index_definition and "UNIQUE INDEX" in index_definition.upper()
            assert "provider = 'bolna'" in index_definition

        with TestClient(app) as client:
            # Existing candidate-level uniqueness race remains protected.
            payload = {
                "full_name": "Synthetic Candidate Intake",
                "phone_number": "+91 98765 43210",
                "job_title": "Concurrent Integration Role",
                "job_description": "Dedicated PostgreSQL integration test.",
                "skills": [],
            }
            candidate_barrier = Barrier(2)

            def wait_for_candidate_duplicate_prechecks(connection, cursor, statement, parameters, context, executemany):
                if (
                    statement.lstrip().upper().startswith("SELECT")
                    and "normalized_phone_number" in statement
                    and "normalized_job_title" in statement
                ):
                    candidate_barrier.wait(timeout=15)

            event.listen(engine, "before_cursor_execute", wait_for_candidate_duplicate_prechecks)
            try:
                def submit_candidate_once():
                    with TestClient(app) as concurrent_client:
                        return concurrent_client.post("/api/candidates", json=payload).status_code
                with ThreadPoolExecutor(max_workers=2) as executor:
                    candidate_statuses = list(executor.map(lambda _: submit_candidate_once(), range(2)))
            finally:
                event.remove(engine, "before_cursor_execute", wait_for_candidate_duplicate_prechecks)
            assert sorted(candidate_statuses) == [201, 409]

            provider_lock = Lock()
            provider_creations = []

            def mocked_bolna_request(request):
                with provider_lock:
                    provider_creations.append(request.method)
                if request.method == "POST":
                    return httpx.Response(200, json={"execution_id": str(uuid4()), "status": "queued"})
                return httpx.Response(200, json={"status": "completed", "transcript": "Synthetic."})

            provider_http = httpx.Client(transport=httpx.MockTransport(mocked_bolna_request))
            bolna_adapter = BolnaAdapter(
                api_key=SecretStr("synthetic-postgres-test-key"),
                agent_id="synthetic-test-agent", enabled=True, client=provider_http,
            )
            previous_bolna_override = app.dependency_overrides.get(get_enabled_bolna_adapter)
            app.dependency_overrides[get_enabled_bolna_adapter] = lambda: bolna_adapter

            def create_candidate_and_sessions(title: str, session_count: int) -> tuple[str, list[str]]:
                create_response = client.post("/api/candidates", json={
                    "full_name": f"Synthetic {title}",
                    "phone_number": "+91 90000 " + str(20000 + session_count),
                    "job_title": title,
                    "job_description": "Synthetic PostgreSQL concurrency fixture.",
                    "skills": ["Testing"],
                })
                assert create_response.status_code == 201
                candidate_id = create_response.json()["id"]
                session_ids = []
                for _ in range(session_count):
                    response = client.post("/api/screening-sessions", json={"candidate_id": candidate_id})
                    assert response.status_code == 201
                    session_ids.append(response.json()["id"])
                return candidate_id, session_ids

            def concurrently_start(candidate_id: str, session_ids: list[str]) -> list[int]:
                start_barrier = Barrier(len(session_ids))

                def align_application_prechecks(connection, cursor, statement, parameters, context, executemany):
                    values = parameters.values() if isinstance(parameters, dict) else parameters
                    if (
                        statement.lstrip().upper().startswith("SELECT")
                        and "FROM calls" in statement
                        and "calls.candidate_id" in statement
                        and "calls.provider" in statement
                        and "calls.status" not in statement
                        and "idempotency_key" not in statement
                        and "bolna" in values
                    ):
                        start_barrier.wait(timeout=20)

                event.listen(engine, "before_cursor_execute", align_application_prechecks)
                try:
                    def submit_for_session(session_id: str) -> int:
                        start_barrier.wait(timeout=20)
                        with TestClient(app) as concurrent_client:
                            return concurrent_client.post(
                                f"/api/screening-sessions/{session_id}/bolna-call"
                            ).status_code
                    with ThreadPoolExecutor(max_workers=len(session_ids)) as executor:
                        return list(executor.map(submit_for_session, session_ids))
                finally:
                    event.remove(engine, "before_cursor_execute", align_application_prechecks)

            try:
                # Four requests sharing one screening-session key: one provider
                # initiation; all other HTTP requests return the existing call.
                same_candidate, same_sessions = create_candidate_and_sessions("Concurrent Same Session", 1)
                same_session_statuses = concurrently_start(same_candidate, [same_sessions[0]] * 4)
                assert same_session_statuses.count(201) == 1
                assert same_session_statuses.count(200) == 3
                assert len(provider_creations) == 1

                # Four distinct sessions for the same application race past
                # application checks; PostgreSQL's partial unique index wins.
                different_candidate, different_sessions = create_candidate_and_sessions(
                    "Concurrent Different Sessions", 4
                )
                different_session_statuses = concurrently_start(different_candidate, different_sessions)
                assert different_session_statuses.count(201) == 1
                assert different_session_statuses.count(409) == 3
                assert len(provider_creations) == 2

                with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
                    assert db.scalar(text(
                        "SELECT count(*) FROM calls WHERE provider = 'bolna' AND candidate_id = :candidate_id"
                    ), {"candidate_id": UUID(same_candidate)}) == 1
                    assert db.scalar(text(
                        "SELECT count(*) FROM calls WHERE provider = 'bolna' AND candidate_id = :candidate_id"
                    ), {"candidate_id": UUID(different_candidate)}) == 1
                    assert db.scalar(text(
                        "SELECT count(*) FROM screening_sessions WHERE candidate_id = :candidate_id AND call_id IS NOT NULL"
                    ), {"candidate_id": UUID(different_candidate)}) == 1

                # Two explicit syncs race on one original execution. They can
                # only GET; the final persisted state must not regress.
                with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
                    bolna_call = db.scalar(select(Call).where(
                        Call.provider == "bolna", Call.candidate_id == UUID(different_candidate)
                    ))
                    bolna_call.status = CallStatus.FINALIZING.value
                    db.commit()
                    call_id = str(bolna_call.id)
                before_sync_requests = len(provider_creations)
                sync_barrier = Barrier(2)
                sync_statuses = []
                def sync_once():
                    sync_barrier.wait(timeout=15)
                    with TestClient(app) as concurrent_client:
                        response = concurrent_client.post(f"/api/calls/{call_id}/bolna-sync")
                        return response.status_code
                with ThreadPoolExecutor(max_workers=2) as executor:
                    sync_statuses = list(executor.map(lambda _: sync_once(), range(2)))
                assert sync_statuses == [200, 200] or sorted(sync_statuses) == [200, 200]
                assert len(provider_creations) == before_sync_requests + 2
                assert provider_creations[-2:] == ["GET", "GET"]
                with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
                    assert db.get(Call, UUID(call_id)).status == CallStatus.COMPLETED.value
            finally:
                bolna_adapter.close()
                provider_http.close()
                if previous_bolna_override is None:
                    app.dependency_overrides.pop(get_enabled_bolna_adapter, None)
                else:
                    app.dependency_overrides[get_enabled_bolna_adapter] = previous_bolna_override

        # Downgrade must refuse both finalizing statuses and retained results.
        protected_candidate_id = uuid4()
        protected_call_id = uuid4()
        protected_session_id = uuid4()
        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
            candidate = Candidate(
                id=protected_candidate_id, full_name="Synthetic Protected Result",
                phone_number="+91 90000 30001", normalized_phone_number="+919000030001",
                job_title="Protected Migration Role", normalized_job_title="protected migration role",
                job_description="Synthetic downgrade safety fixture.", skills=[],
            )
            call = Call(
                id=protected_call_id, candidate_id=protected_candidate_id, provider="bolna",
                provider_call_id=str(uuid4()), idempotency_key="protected-finalizing-call",
                status=CallStatus.FINALIZING.value,
            )
            db.add_all([candidate, call])
            db.flush()
            screening = ScreeningSession(
                id=protected_session_id, candidate_id=protected_candidate_id, call_id=protected_call_id,
                status="created", question_config=[], provider_transcript="Synthetic transcript",
                provider_summary="Synthetic summary", provider_extracted_data={"x": "y"},
                provider_call_duration_seconds=10,
            )
            db.add(screening)
            db.commit()
        with pytest.raises(RuntimeError, match="finalizing status"):
            command.downgrade(alembic_config, "0006_screening_conversations")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM calls WHERE id = :id"), {"id": protected_call_id}) == 1
            assert connection.scalar(text("SELECT provider_transcript FROM screening_sessions WHERE id = :id"), {"id": protected_session_id}) == "Synthetic transcript"

        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
            db.get(Call, protected_call_id).status = CallStatus.COMPLETED.value
            db.commit()
        with pytest.raises(RuntimeError, match="contain retrieved provider results"):
            command.downgrade(alembic_config, "0006_screening_conversations")

        # Once protected data is explicitly cleared in this disposable test DB,
        # a safe downgrade and re-upgrade should work without schema loss.
        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
            screening = db.get(ScreeningSession, protected_session_id)
            screening.provider_transcript = None
            screening.provider_summary = None
            screening.provider_extracted_data = None
            screening.provider_call_duration_seconds = None
            db.delete(db.get(Call, protected_call_id))
            db.delete(screening)
            db.delete(db.get(Candidate, protected_candidate_id))
            db.commit()
        command.downgrade(alembic_config, "0006_screening_conversations")
        command.upgrade(alembic_config, "head")
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        app.dependency_overrides.pop(get_enabled_bolna_adapter, None)
        main_module.engine = previous_engine
        if migration_attempted:
            with engine.begin() as connection:
                version = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if version == "0007_bolna_finalization":
                    connection.execute(text("UPDATE calls SET status = 'completed' WHERE status = 'finalizing'"))
                    connection.execute(text(
                        "UPDATE screening_sessions SET provider_transcript = NULL, provider_summary = NULL, "
                        "provider_extracted_data = NULL, provider_call_duration_seconds = NULL"
                    ))
            command.downgrade(alembic_config, "base")
        engine.dispose()
