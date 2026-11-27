from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Candidate
from app.routes import DUPLICATE_CONSTRAINT, DUPLICATE_MESSAGE


def valid_candidate(**overrides):
    payload = {
        "full_name": "Asha Rao",
        "phone_number": "+91 98765 43210",
        "email": "asha@example.com",
        "job_title": "Backend Engineer",
        "job_description": "Build and maintain API services.",
        "years_of_experience": 4.5,
        "skills": ["Python", "FastAPI"],
        "location": "Bengaluru",
    }
    return payload | overrides


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health(client):
    response = client.get("/health/database")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_retrieve_and_list_candidate(client):
    created = client.post("/api/candidates", json=valid_candidate())
    assert created.status_code == 201
    candidate = created.json()
    assert candidate["full_name"] == "Asha Rao"
    assert candidate["years_of_experience"] == "4.5"
    assert candidate["skills"] == ["Python", "FastAPI"]

    retrieved = client.get(f"/api/candidates/{candidate['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["id"] == candidate["id"]

    listed = client.get("/api/candidates?limit=10&offset=0")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == candidate["id"]


def test_optional_fields_and_comma_separated_skills(client):
    payload = valid_candidate(email="", years_of_experience=None, location="", skills=" Python, , SQL ")
    response = client.post("/api/candidates", json=payload)
    assert response.status_code == 201
    assert response.json()["email"] is None
    assert response.json()["location"] is None
    assert response.json()["skills"] == ["Python", "SQL"]


def test_required_field_validation(client):
    payload = valid_candidate()
    del payload["job_title"]
    response = client.post("/api/candidates", json=payload)
    assert response.status_code == 422


def test_invalid_phone_validation(client):
    response = client.post("/api/candidates", json=valid_candidate(phone_number="abc"))
    assert response.status_code == 422
    assert "valid phone number" in response.json()["detail"][0]["msg"].lower()


def test_same_phone_and_same_role_is_rejected(client):
    first = client.post("/api/candidates", json=valid_candidate())
    assert first.status_code == 201

    duplicate = client.post("/api/candidates", json=valid_candidate())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == DUPLICATE_MESSAGE


def test_same_phone_can_apply_for_different_roles(client):
    assert client.post("/api/candidates", json=valid_candidate()).status_code == 201
    another_role = client.post(
        "/api/candidates", json=valid_candidate(job_title="Frontend Engineer")
    )
    assert another_role.status_code == 201


def test_different_phone_can_apply_for_same_role(client):
    assert client.post("/api/candidates", json=valid_candidate()).status_code == 201
    another_candidate = client.post(
        "/api/candidates", json=valid_candidate(phone_number="+91 91234 56780")
    )
    assert another_candidate.status_code == 201


def test_phone_formatting_and_default_india_region_are_normalized(client):
    assert client.post("/api/candidates", json=valid_candidate(phone_number="98765 43210")).status_code == 201
    duplicate = client.post(
        "/api/candidates", json=valid_candidate(phone_number="(+91) 98765-43210")
    )
    assert duplicate.status_code == 409


def test_job_title_case_and_whitespace_are_normalized(client):
    first = client.post("/api/candidates", json=valid_candidate(job_title="  Backend   Engineer  "))
    assert first.status_code == 201
    assert first.json()["job_title"] == "Backend   Engineer"
    duplicate = client.post(
        "/api/candidates", json=valid_candidate(job_title="backend    ENGINEER")
    )
    assert duplicate.status_code == 409


def test_unique_constraint_violation_after_precheck_is_returned_as_conflict(client):
    # Simulate another request inserting the same keys after this request's pre-check.
    class UniqueViolation(Exception):
        diag = SimpleNamespace(constraint_name=DUPLICATE_CONSTRAINT)

    mock_db = SimpleNamespace(
        scalar=lambda statement: None,
        add=lambda candidate: None,
        commit=lambda: (_ for _ in ()).throw(IntegrityError("INSERT", {}, UniqueViolation())),
        rollback=lambda: None,
    )

    def override_db():
        yield mock_db

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post("/api/candidates", json=valid_candidate())
    finally:
        app.dependency_overrides[get_db] = previous

    assert response.status_code == 409
    assert response.json()["detail"] == DUPLICATE_MESSAGE


def test_unrelated_database_error_is_not_reported_as_duplicate(client):
    mock_db = SimpleNamespace(
        scalar=lambda statement: None,
        add=lambda candidate: None,
        commit=lambda: (_ for _ in ()).throw(
            OperationalError("INSERT", {}, Exception("database unavailable"))
        ),
        rollback=lambda: None,
    )

    def override_db():
        yield mock_db

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post("/api/candidates", json=valid_candidate())
    finally:
        app.dependency_overrides[get_db] = previous

    assert response.status_code == 503
    assert response.json()["detail"] != DUPLICATE_MESSAGE


def test_concurrent_inserts_are_protected_by_database_unique_constraint(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent-candidates.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = Barrier(2)

    def insert_candidate() -> str:
        with TestSession() as session:
            session.add(
                Candidate(
                    full_name="Candidate",
                    phone_number="+919876543210",
                    normalized_phone_number="+919876543210",
                    job_title="Backend Engineer",
                    normalized_job_title="backend engineer",
                    job_description="Test role",
                )
            )
            barrier.wait(timeout=5)
            try:
                session.commit()
                return "created"
            except IntegrityError:
                session.rollback()
                return "duplicate"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: insert_candidate(), range(2)))
        assert sorted(results) == ["created", "duplicate"]
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM candidates")).scalar_one() == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_migration_reports_existing_duplicates_before_changing_records(tmp_path: Path):
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "0002_prevent_duplicate_applications.py"
    spec = importlib.util.spec_from_file_location("duplicate_application_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine(f"sqlite:///{tmp_path / 'existing-duplicates.db'}")
    first_id = "00000000-0000-0000-0000-000000000001"
    second_id = "00000000-0000-0000-0000-000000000002"
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE candidates (id TEXT PRIMARY KEY, phone_number VARCHAR(32), job_title VARCHAR(200))"
        ))
        connection.execute(
            text("INSERT INTO candidates (id, phone_number, job_title) VALUES (:id, :phone, :title)"),
            [
                {"id": first_id, "phone": "98765 43210", "title": "Backend Engineer"},
                {"id": second_id, "phone": "+91 98765-43210", "title": "backend   ENGINEER"},
            ],
        )

    with engine.connect() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="existing duplicate applications") as error:
                migration.upgrade()

    assert first_id in str(error.value)
    assert second_id in str(error.value)
    assert "No candidate records were changed" in str(error.value)
    with engine.connect() as connection:
        columns = connection.execute(text("PRAGMA table_info(candidates)")).all()
        records = connection.execute(text("SELECT id, phone_number, job_title FROM candidates ORDER BY id")).all()
    assert [row[1] for row in columns] == ["id", "phone_number", "job_title"]
    assert len(records) == 2
    engine.dispose()


def test_invalid_email_validation(client):
    response = client.post("/api/candidates", json=valid_candidate(email="not-an-email"))
    assert response.status_code == 422


def test_years_of_experience_validation(client):
    for value in (-1, 81, "many"):
        response = client.post("/api/candidates", json=valid_candidate(years_of_experience=value))
        assert response.status_code == 422


def test_candidate_not_found_and_invalid_id(client):
    assert client.get(f"/api/candidates/{uuid4()}").status_code == 404
    assert client.get("/api/candidates/not-a-uuid").status_code == 422
