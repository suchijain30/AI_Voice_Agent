from uuid import UUID

import httpx
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app.calls.bolna import BolnaAdapter
from app.calls.bolna_routes import get_enabled_bolna_adapter


def _create_candidate(client):
    response = client.post(
        "/api/candidates",
        json={
            "full_name": "Priya Sharma",
            "phone_number": "+91 98765 11122",
            "email": "priya@example.com",
            "job_title": "Backend Engineer",
            "job_description": "Build FastAPI services and PostgreSQL schemas.",
            "years_of_experience": 5.0,
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "location": "Bengaluru",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_list_candidate_screening_sessions_and_process_results(client):
    candidate = _create_candidate(client)
    first = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"]})
    assert first.status_code == 201
    session_id = first.json()["id"]

    listed = client.get(f"/api/candidates/{candidate['id']}/screening-sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [session_id]

    # No provider data yet -> honest 409 conflict without fabricating results.
    empty_process = client.post(f"/api/screening-sessions/{session_id}/process-results")
    assert empty_process.status_code == 409

    # Completed Bolna sync automatically populates answers, provenance, evaluation, and session status.
    execution_id = "223e4567-e89b-42d3-a456-426614174000"
    queued_payload = {"execution_id": execution_id, "status": "queued"}
    completed_payload = {
        "status": "completed",
        "duration": 145,
        "transcript": "Candidate: Yes, I am exploring opportunities. I have 5 years total and 4 years relevant experience in Python, FastAPI. Expected CTC is 24 LPA and notice period is 30 days. Based in Bengaluru, hybrid works. Available Friday at 3 PM.",
        "summary": "Candidate is interested with 5 years experience and 30-day notice period.",
        "extracted_data": {
            "willing_to_continue": "Yes",
            "exploring_opportunities": "Yes, exploring opportunities",
            "total_experience_years": 5,
            "relevant_experience_years": 4,
            "skills_and_technologies": ["Python", "FastAPI"],
            "expected_compensation": "24 LPA",
            "notice_period": "30 days",
            "location_and_work_arrangement": "Bengaluru, hybrid",
            "interview_availability": "Friday afternoon",
        },
    }

    def handler(request):
        return httpx.Response(200, json=queued_payload if request.method == "POST" else completed_payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = BolnaAdapter(api_key=SecretStr("offline-secret"), agent_id="agent-test", enabled=True, client=http)
    previous = client.app.dependency_overrides.get(get_enabled_bolna_adapter)
    client.app.dependency_overrides[get_enabled_bolna_adapter] = lambda: adapter
    try:
        call_resp = client.post(f"/api/screening-sessions/{session_id}/bolna-call")
        assert call_resp.status_code == 201
        call_id = call_resp.json()["id"]

        sync_resp = client.post(f"/api/calls/{call_id}/bolna-sync")
        assert sync_resp.status_code == 200
        assert sync_resp.json()["result_available"] is True
    finally:
        adapter.close()
        http.close()
        if previous is None:
            client.app.dependency_overrides.pop(get_enabled_bolna_adapter, None)
        else:
            client.app.dependency_overrides[get_enabled_bolna_adapter] = previous

    session_resp = client.get(f"/api/screening-sessions/{session_id}")
    assert session_resp.status_code == 200
    assert session_resp.json()["status"] == "completed"
    assert session_resp.json()["provider_call_duration_seconds"] == 145

    answers_resp = client.get(f"/api/screening-sessions/{session_id}/answers")
    assert answers_resp.status_code == 200
    answers_by_key = {item["question_key"]: item for item in answers_resp.json()}
    assert answers_by_key["notice_period"]["information_source"] == "explicit"
    assert answers_by_key["interview_availability"]["information_source"] == "inferred"

    eval_resp = client.get(f"/api/screening-sessions/{session_id}/evaluation")
    assert eval_resp.status_code == 200
    evaluation = eval_resp.json()
    assert evaluation["advisory_recommendation"] == "proceed_to_human_review"
    assert evaluation["total_experience_years"] == 5.0
    assert evaluation["relevant_experience_years"] == 4.0
    assert evaluation["skills"] == ["Python", "FastAPI"]
    assert evaluation["field_sources"]["notice_period"] == "explicit"
    assert "current compensation" in evaluation["missing_information"]
