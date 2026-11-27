import pytest
from pydantic import ValidationError

from app.intelligence.mock import MockIntelligenceProvider
from app.intelligence.schemas import InterpretationContext, ResponseInterpretation


def _context(raw_response="Synthetic response.", state="awaiting_response"):
    return InterpretationContext(
        question_key="experience", question_text="How much experience do you have?",
        question_category="experience", question_required=True, raw_response=raw_response,
        job_title="Synthetic role", conversation_state=state,
        clarification_attempt_count=0, max_clarification_attempts=2,
    )


def _candidate(client, phone="+91 98765 43210"):
    response = client.post("/api/candidates", json={
        "full_name": "Synthetic Intelligence Test Candidate", "phone_number": phone,
        "email": None, "job_title": "Synthetic role", "job_description": "Synthetic test role.",
        "skills": ["Python"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _session(client, *, phone="+91 98765 43210", questions=None):
    candidate = _candidate(client, phone)
    questions = questions or [{
        "question_key": "experience", "question_text": "How much experience do you have?",
        "required": True, "order": 0, "category": "experience",
    }]
    response = client.post("/api/screening-sessions", json={"candidate_id": candidate["id"], "questions": questions})
    assert response.status_code == 201, response.text
    session = response.json()
    start = client.post(f"/api/screening-sessions/{session['id']}/conversation", json={})
    assert start.status_code == 200, start.text
    return session


def _respond(client, session_id, scenario, text="Synthetic response.", question_key="experience"):
    return client.post(
        f"/api/screening-sessions/{session_id}/conversation/response",
        json={"question_key": question_key, "intelligence_scenario": scenario, "response_text": text},
    )


def _answers(client, session_id):
    return client.get(f"/api/screening-sessions/{session_id}/answers").json()


def _history(client, session_id):
    return client.get(f"/api/screening-sessions/{session_id}/conversation/turns").json()


def test_mock_is_deterministic_and_does_not_infer_arbitrary_language():
    context = _context("Any arbitrary words.")
    first = MockIntelligenceProvider("clear_answer").interpret(context)
    assert first == MockIntelligenceProvider("clear_answer").interpret(context)
    assert first.original_response == "Any arbitrary words."
    assert first.extracted_answer is None


def test_fixed_example_extraction_is_explicit_and_structured():
    result = MockIntelligenceProvider("experience_five_years_example").interpret(
        _context("I started working in 2021, so around five years.")
    )
    assert result.extracted_answer == "approximately five years"
    assert result.normalized_answer == {"value": 5, "unit": "years", "approximate": True}
    assert result.information_source == "explicit"
    assert result.confidence == 0.88


def test_configured_fixture_can_express_inferred_provenance_without_default_fabrication():
    fixture = {
        "disposition": "answer", "extracted_answer": "fixture value",
        "normalized_answer": {"test_fixture": True}, "information_source": "inferred",
        "is_missing": False,
    }
    result = MockIntelligenceProvider("configured_case", fixtures={"configured_case": fixture}).interpret(
        _context("Synthetic fixture text.")
    )
    assert result.information_source == "inferred"
    assert result.extracted_answer == "fixture value"


def test_schema_rejects_invalid_confidence_classification_and_provenance():
    with pytest.raises(ValidationError):
        ResponseInterpretation(original_response="x", disposition="answer", question_key="experience",
                               information_source="explicit", confidence=1.1)
    with pytest.raises(ValidationError):
        ResponseInterpretation(original_response="x", disposition="answer", question_key="experience")
    with pytest.raises(ValidationError):
        ResponseInterpretation(original_response="x", disposition="unsupported", question_key="experience")


def test_interpreted_extraction_is_persisted(client):
    session = _session(client)
    result = _respond(client, session["id"], "experience_five_years_example",
                      "I started working in 2021, so around five years.")
    assert result.status_code == 200, result.text
    assert result.json()["used_safe_fallback"] is False
    answer = _answers(client, session["id"])[0]
    assert answer["original_response"] == "I started working in 2021, so around five years."
    assert answer["normalized_value"] == {"value": 5, "unit": "years", "approximate": True}
    assert answer["information_source"] == "explicit" and answer["confidence"] == 0.88


@pytest.mark.parametrize("scenario", [
    "timeout", "provider_failure", "invalid_output", "invalid_confidence",
    "unsupported_classification", "wrong_question_key", "unknown_scenario",
])
def test_invalid_or_failed_interpretation_falls_back_safely(client, scenario):
    session = _session(client)
    result = _respond(client, session["id"], scenario, "Keep this raw response.")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["used_safe_fallback"] is True
    assert data["interpretation"]["disposition"] == "unclear"
    assert data["interpretation"]["question_key"] == "experience"
    assert data["conversation"]["state"] == "clarification_needed"
    assert "Keep this raw response." in [turn["message_text"] for turn in _history(client, session["id"])]
    assert _answers(client, session["id"]) == []


def test_unclear_then_clarification_answer_uses_existing_orchestrator(client):
    session = _session(client)
    first = _respond(client, session["id"], "unclear", "Not sure.")
    assert first.status_code == 200 and first.json()["conversation"]["state"] == "clarification_needed"
    second = _respond(client, session["id"], "clear_answer", "About four years.")
    assert second.status_code == 200 and second.json()["outcome"] == "screening_completed"
    assert _answers(client, session["id"])[0]["original_response"] == "About four years."


def test_repeat_refusal_stop_and_no_answer_never_fabricate_answers(client):
    repeated = _session(client)
    result = _respond(client, repeated["id"], "question_repeat_requested", "Repeat that please.")
    assert result.status_code == 200 and result.json()["outcome"] == "question_repeated"
    assert _answers(client, repeated["id"]) == []

    refused = _session(client, phone="+91 91234 56780")
    result = _respond(client, refused["id"], "candidate_declined", "I prefer not to answer.")
    assert result.status_code == 200 and _answers(client, refused["id"])[0]["is_missing"] is True

    stopped = _session(client, phone="+91 92234 56780")
    result = _respond(client, stopped["id"], "candidate_wants_to_stop", "Please stop.")
    assert result.status_code == 200 and result.json()["conversation"]["state"] == "declined"

    unanswered = _session(client, phone="+91 93234 56780")
    result = _respond(client, unanswered["id"], "no_answer", None)
    assert result.status_code == 200 and result.json()["conversation"]["state"] == "clarification_needed"
    assert _answers(client, unanswered["id"]) == []


def test_wrong_active_question_key_is_rejected_before_interpretation(client):
    questions = [
        {"question_key": "first_question", "question_text": "First?", "required": True, "order": 0, "category": "test"},
        {"question_key": "second_question", "question_text": "Second?", "required": True, "order": 1, "category": "test"},
    ]
    session = _session(client, questions=questions)
    result = _respond(client, session["id"], "clear_answer", "Stale", "second_question")
    assert result.status_code == 409
    current = client.get(f"/api/screening-sessions/{session['id']}/conversation").json()
    assert current["current_question_key"] == "first_question"


def test_legacy_manual_response_shape_still_works(client):
    session = _session(client)
    response = client.post(
        f"/api/screening-sessions/{session['id']}/conversation/response",
        json={"question_key": "experience", "disposition": "answer", "response_text": "Six years."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["interpretation"] is None


def test_context_limits_are_enforced_and_zero_turn_limit_is_supported():
    from app.config import IntelligenceSettings
    from app.intelligence.context import InterpretationContextBuilder
    from app.intelligence.errors import IntelligenceContextError
    from app.conversations.service import ConversationInterpretationSource
    from app.screenings.schemas import ScreeningQuestion

    source = ConversationInterpretationSource(
        question=ScreeningQuestion(question_key="experience", question_text="Question?", category="experience",
                                   required=True, order=0),
        conversation_state="awaiting_response", clarification_attempts=0, max_clarification_attempts=2,
        job_title="Role", job_description="", previous_turns=(),
    )
    settings = IntelligenceSettings(intelligence_max_context_turns=0)
    built = InterpretationContextBuilder(settings).build(source, question_key="experience", raw_response="ok")
    assert built.previous_turns == []
    with pytest.raises(IntelligenceContextError):
        InterpretationContextBuilder(IntelligenceSettings(intelligence_max_response_chars=1)).build(
            source, question_key="experience", raw_response="too long"
        )


def test_ai_unclear_responses_obey_existing_clarification_cap(client):
    session = _session(client)
    first = _respond(client, session["id"], "unclear", "No estimate.")
    assert first.status_code == 200
    second = _respond(client, session["id"], "unclear", "Still cannot say.")
    assert second.status_code == 200
    assert second.json()["conversation"]["state"] == "incomplete"
    assert _answers(client, session["id"])[0]["is_missing"] is True
    assert [turn["message_text"] for turn in _history(client, session["id"])].count("No estimate.") == 1
    assert "Still cannot say." in [turn["message_text"] for turn in _history(client, session["id"])]
