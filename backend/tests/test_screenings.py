from uuid import UUID

import pytest
from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.calls.providers import MockProvider
from app.calls.routes import get_call_service
from app.calls.service import CallLifecycleService
from app.database import get_db
from app.main import app
from app.models import Call
from app.screenings.questions import INITIAL_SCREENING_QUESTIONS
from app.screenings.schemas import (
    ScreeningAnswerUpsert,
    ScreeningEvaluationInput,
    ScreeningQuestion,
    ScreeningSessionCreate,
)
from app.screenings.service import ScreeningService
from app.screenings.types import ScreeningSessionStatus


def candidate_payload(**changes):
    payload = {
        "full_name": "Screening Test Candidate",
        "phone_number": "+91 98765 43210",
        "email": "screening@example.test",
        "job_title": "Platform Engineer",
        "job_description": "Synthetic role for screening workflow tests.",
        "skills": ["Python", "PostgreSQL"],
    }
    return payload | changes


def create_candidate(client, **changes):
    response = client.post("/api/candidates", json=candidate_payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def create_session(client, candidate_id, **changes):
    response = client.post("/api/screening-sessions", json={"candidate_id": candidate_id, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def optional_test_question():
    return [{
        "question_key": "test_optional_question",
        "question_text": "Optional synthetic test question?",
        "required": False,
        "order": 0,
        "category": "test",
        "follow_up_guidance": None,
    }]


def test_initial_question_configuration_is_valid_and_extensible():
    assert len(INITIAL_SCREENING_QUESTIONS) >= 8
    keys = [question.question_key for question in INITIAL_SCREENING_QUESTIONS]
    assert len(keys) == len(set(keys))
    assert [question.order for question in INITIAL_SCREENING_QUESTIONS] == list(range(len(keys)))
    custom = ScreeningQuestion(
        question_key="portfolio_link",
        question_text="Would you like to share a portfolio?",
        required=False,
        order=0,
        category="role_specific",
        follow_up_guidance="Accept a link only if the candidate offers one.",
    )
    assert custom.category == "role_specific"


def test_question_configuration_rejects_duplicate_keys_and_orders():
    question = INITIAL_SCREENING_QUESTIONS[0].model_dump()
    with pytest.raises(ValidationError, match="Question keys must be unique"):
        ScreeningSessionCreate(
            candidate_id=UUID(int=1),
            questions=[question, question | {"order": 1}],
        )
    with pytest.raises(ValidationError, match="Question order values must be unique"):
        ScreeningSessionCreate(
            candidate_id=UUID(int=1),
            questions=[question, question | {"question_key": "another_question"}],
        )


def test_session_creation_snapshots_default_or_custom_questions(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    assert session["status"] == "created"
    assert session["candidate_id"] == candidate["id"]
    assert session["call_id"] is None
    assert len(session["questions"]) == len(INITIAL_SCREENING_QUESTIONS)

    custom = [{
        "question_key": "portfolio_link",
        "question_text": "Do you have a portfolio?",
        "required": False,
        "order": 0,
        "category": "role_specific",
        "follow_up_guidance": None,
    }]
    custom_session = create_session(client, candidate["id"], questions=custom)
    fetched = client.get(f"/api/screening-sessions/{custom_session['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["questions"] == custom


def test_session_candidate_and_optional_call_relationship_validation(client):
    candidate_a = create_candidate(client)
    candidate_b = create_candidate(
        client,
        full_name="Other Candidate",
        phone_number="+91 91234 56780",
        email="other@example.test",
    )
    previous = app.dependency_overrides.get(get_call_service)

    def enabled_mock_calls(db: Session = Depends(get_db)):
        return CallLifecycleService(db, MockProvider(), enabled=True)

    app.dependency_overrides[get_call_service] = enabled_mock_calls
    try:
        call_response = client.post(
            f"/api/candidates/{candidate_a['id']}/calls",
            headers={"Idempotency-Key": "screening-call-link-test"},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_call_service, None)
        else:
            app.dependency_overrides[get_call_service] = previous
    assert call_response.status_code == 201
    call_id = call_response.json()["id"]
    linked = create_session(client, candidate_a["id"], call_id=call_id)
    assert linked["call_id"] == call_id

    mismatch = client.post(
        "/api/screening-sessions", json={"candidate_id": candidate_b["id"], "call_id": call_id}
    )
    assert mismatch.status_code == 409
    missing_candidate = client.post(
        "/api/screening-sessions", json={"candidate_id": str(UUID(int=100))}
    )
    assert missing_candidate.status_code == 404
    missing_call = client.post(
        "/api/screening-sessions",
        json={"candidate_id": candidate_a["id"], "call_id": str(UUID(int=101))},
    )
    assert missing_call.status_code == 404


def test_screening_status_transitions_and_invalid_transition(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"], questions=optional_test_question())
    in_progress = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "in_progress"}
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["started_at"] is not None
    completed = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "completed"}
    )
    assert completed.status_code == 200
    assert completed.json()["ended_at"] is not None
    invalid = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "in_progress"}
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"].startswith("Screening session cannot transition")


@pytest.mark.parametrize("terminal", ["declined", "disconnected", "incomplete"])
def test_alternate_session_terminal_states(client, terminal):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    response = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": terminal}
    )
    assert response.status_code == 200
    assert response.json()["status"] == terminal
    assert response.json()["ended_at"] is not None


def test_required_answers_block_completion_until_recorded(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    client.post(f"/api/screening-sessions/{session['id']}/status", json={"status": "in_progress"})
    blocked = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "completed"}
    )
    assert blocked.status_code == 409
    assert "willing_to_continue" in blocked.json()["detail"]

    saved = client.post(
        f"/api/screening-sessions/{session['id']}/answers/willing_to_continue",
        json={
            "original_response": "Yes, I am willing to continue.",
            "normalized_value": True,
            "information_source": "explicit",
        },
    )
    assert saved.status_code == 200
    blocked_again = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "completed"}
    )
    assert blocked_again.status_code == 409


def test_missing_required_answer_requires_incomplete_not_completed(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    client.post(f"/api/screening-sessions/{session['id']}/status", json={"status": "in_progress"})
    client.post(
        f"/api/screening-sessions/{session['id']}/answers/willing_to_continue",
        json={"is_missing": True},
    )
    blocked = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "completed"}
    )
    assert blocked.status_code == 409
    assert "willing_to_continue" in blocked.json()["detail"]


def test_answer_upsert_preserves_original_and_explicit_or_inferred_provenance(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    started = client.post(
        f"/api/screening-sessions/{session['id']}/status", json={"status": "in_progress"}
    )
    assert started.status_code == 200
    url = f"/api/screening-sessions/{session['id']}/answers/total_experience_years"
    explicit = client.post(
        url,
        json={
            "original_response": "About six years.",
            "normalized_value": 6,
            "information_source": "explicit",
            "confidence": 0.99,
        },
    )
    assert explicit.status_code == 200
    assert explicit.json()["original_response"] == "About six years."
    assert explicit.json()["normalized_value"] == 6
    assert explicit.json()["information_source"] == "explicit"

    inferred = client.post(
        f"/api/screening-sessions/{session['id']}/answers/relevant_experience_years",
        json={
            "original_response": "I spent four years building similar systems.",
            "normalized_value": 4,
            "information_source": "inferred",
            "confidence": 0.72,
        },
    )
    assert inferred.status_code == 200
    answers = client.get(f"/api/screening-sessions/{session['id']}/answers")
    assert answers.status_code == 200
    assert [item["question_key"] for item in answers.json()][:2] == [
        "total_experience_years",
        "relevant_experience_years",
    ]


def test_missing_answer_has_no_fabricated_values_and_unknown_question_rejected(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    response = client.post(
        f"/api/screening-sessions/{session['id']}/answers/current_compensation",
        json={"is_missing": True},
    )
    assert response.status_code == 200
    assert response.json()["is_missing"] is True
    assert response.json()["original_response"] is None
    assert response.json()["normalized_value"] is None
    invalid = client.post(
        f"/api/screening-sessions/{session['id']}/answers/unknown_question",
        json={"is_missing": True},
    )
    assert invalid.status_code == 422
    invalid_missing = client.post(
        f"/api/screening-sessions/{session['id']}/answers/current_compensation",
        json={"is_missing": True, "normalized_value": "estimated"},
    )
    assert invalid_missing.status_code == 422
    invalid_source = client.post(
        f"/api/screening-sessions/{session['id']}/answers/current_compensation",
        json={"original_response": "Not sure", "information_source": "fabricated"},
    )
    assert invalid_source.status_code == 422


def evaluation_payload(**changes):
    return {
        "total_experience_years": 6,
        "relevant_experience_years": 4,
        "skills": ["Python", "PostgreSQL"],
        "current_compensation": None,
        "expected_compensation": "₹24 lakh per year",
        "notice_period": "30 days",
        "location": "Pune",
        "work_arrangement_preference": "Hybrid",
        "work_arrangement_compatibility": "unclear",
        "interest_level": "interested",
        "interview_availability": "Weekday afternoons",
        "field_sources": {
            "total_experience_years": "explicit",
            "relevant_experience_years": "explicit",
            "skills": "explicit",
            "expected_compensation": "explicit",
            "notice_period": "explicit",
            "location": "explicit",
            "work_arrangement_preference": "explicit",
            "work_arrangement_compatibility": "inferred",
            "interest_level": "explicit",
            "interview_availability": "explicit",
        },
        "missing_information": ["current_compensation"],
        "screening_summary": "Candidate described relevant platform engineering experience.",
        "advisory_recommendation": "proceed_to_human_review",
        "recommendation_reason": "Recruiter review may clarify role fit and compensation.",
        "suggested_next_action": "A recruiter may review the answers and decide whether to follow up.",
    } | changes


def test_evaluation_validation_and_retrieval_is_advisory(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"], questions=optional_test_question())
    unavailable = client.post(
        f"/api/screening-sessions/{session['id']}/evaluation", json=evaluation_payload()
    )
    assert unavailable.status_code == 409
    for next_status in ("in_progress", "completed"):
        changed = client.post(
            f"/api/screening-sessions/{session['id']}/status", json={"status": next_status}
        )
        assert changed.status_code == 200

    invalid = client.post(
        f"/api/screening-sessions/{session['id']}/evaluation",
        json=evaluation_payload(total_experience_years=2, relevant_experience_years=3),
    )
    assert invalid.status_code == 422
    saved = client.post(
        f"/api/screening-sessions/{session['id']}/evaluation", json=evaluation_payload()
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["candidate_name"] == candidate["full_name"]
    assert body["job_title"] == candidate["job_title"]
    assert body["advisory_recommendation"] == "proceed_to_human_review"

    fetched = client.get(f"/api/screening-sessions/{session['id']}/evaluation")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_evaluation_requires_provenance_for_populated_candidate_fields():
    payload = evaluation_payload()
    payload["field_sources"] = {}
    with pytest.raises(ValidationError, match="Provide explicit or inferred provenance"):
        ScreeningEvaluationInput.model_validate(payload)


def test_answers_cannot_change_after_session_ends_and_evaluation_missing(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    client.post(f"/api/screening-sessions/{session['id']}/status", json={"status": "declined"})
    answer = client.post(
        f"/api/screening-sessions/{session['id']}/answers/willing_to_continue",
        json={"is_missing": True},
    )
    assert answer.status_code == 409
    evaluation = client.get(f"/api/screening-sessions/{session['id']}/evaluation")
    assert evaluation.status_code == 404


def test_session_read_includes_call_and_candidate_ids(client):
    candidate = create_candidate(client)
    session = create_session(client, candidate["id"])
    response = client.get(f"/api/screening-sessions/{session['id']}")
    assert response.status_code == 200
    assert response.json()["candidate_id"] == candidate["id"]
    assert response.json()["status"] == ScreeningSessionStatus.CREATED.value

