from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


def candidate_data():
    return {
        "full_name": "Simulation Candidate",
        "phone_number": "+91 98765 43210",
        "email": "simulation@example.test",
        "job_title": "Data Platform Engineer",
        "job_description": "Synthetic role used only in local conversation tests.",
        "skills": ["Python"],
    }


def create_candidate(client: TestClient, **overrides):
    response = client.post("/api/candidates", json=candidate_data() | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def question(key: str, order: int, *, required: bool = True):
    return {
        "question_key": key,
        "question_text": f"Please tell me about {key.replace('_', ' ')}.",
        "required": required,
        "order": order,
        "category": "test_role",
        "follow_up_guidance": f"Clarify {key.replace('_', ' ')} if needed.",
    }


def create_screening(client: TestClient, *, questions=None, candidate_overrides=None):
    candidate = create_candidate(client, **(candidate_overrides or {}))
    response = client.post(
        "/api/screening-sessions",
        json={"candidate_id": candidate["id"], "questions": questions or [question("experience", 0)]},
    )
    assert response.status_code == 201, response.text
    return candidate, response.json()


def start_conversation(client: TestClient, session_id: str, max_attempts=2):
    response = client.post(
        f"/api/screening-sessions/{session_id}/conversation",
        json={"max_clarification_attempts": max_attempts},
    )
    assert response.status_code == 200, response.text
    return response.json()


def respond(client: TestClient, session_id: str, disposition: str, response_text=None):
    active = client.get(f"/api/screening-sessions/{session_id}/conversation").json()
    question_key = active.get("current_question_key")
    if question_key is None:
        prior_turns = history(client, session_id)
        question_key = next((turn["question_key"] for turn in reversed(prior_turns) if turn["question_key"]), "experience")
    return client.post(
        f"/api/screening-sessions/{session_id}/conversation/response",
        json={
            "question_key": question_key,
            "disposition": disposition,
            "response_text": response_text,
        },
    )


def history(client: TestClient, session_id: str):
    response = client.get(f"/api/screening-sessions/{session_id}/conversation/turns")
    assert response.status_code == 200, response.text
    return response.json()


def test_create_initial_prompt_resume_and_history_are_idempotent(client):
    candidate, session = create_screening(client)
    started = start_conversation(client, session["id"])
    prompt = started["prompt"]
    assert started["conversation"]["state"] == "awaiting_response"
    assert prompt["question_key"] == "experience"
    assert prompt["question_index"] == 1 and prompt["total_questions"] == 1
    assert prompt["required"] is True
    assert prompt["follow_up_guidance"] == "Clarify experience if needed."
    assert prompt["spoken_wording"].startswith(
        f"Hello, I'm the AI recruitment assistant calling about the {candidate['job_title']} role."
    )

    fetched = client.get(f"/api/screening-sessions/{session['id']}/conversation")
    assert fetched.status_code == 200
    assert fetched.json()["current_prompt"]["spoken_wording"] == prompt["spoken_wording"]
    resumed = start_conversation(client, session["id"])
    assert resumed["outcome"] == "resumed"
    assert len(history(client, session["id"])) == 1
    screening = client.get(f"/api/screening-sessions/{session['id']}").json()
    assert screening["status"] == "in_progress"


def test_required_first_order_optional_questions_and_completion(client):
    questions = [question("optional_first", 0, required=False), question("required_one", 1), question("required_two", 2)]
    _, session = create_screening(client, questions=questions)
    started = start_conversation(client, session["id"])
    assert started["prompt"]["question_key"] == "required_one"
    assert started["prompt"]["question_index"] == 2

    first = respond(client, session["id"], "answer", "Seven years of experience.")
    assert first.status_code == 200
    assert first.json()["prompt"]["question_key"] == "required_two"
    second = respond(client, session["id"], "answer", "Five years are relevant.")
    assert second.status_code == 200
    assert second.json()["prompt"]["question_key"] == "optional_first"
    assert second.json()["prompt"]["required"] is False

    skipped = respond(client, session["id"], "skip")
    assert skipped.status_code == 200
    assert skipped.json()["conversation"]["state"] == "completed"
    screening = client.get(f"/api/screening-sessions/{session['id']}").json()
    assert screening["status"] == "completed"
    turns = history(client, session["id"])
    assert [item["turn_number"] for item in turns] == list(range(1, len(turns) + 1))
    assert [item["question_key"] for item in turns if item["turn_type"] == "question"] == [
        "required_one",
        "required_two",
        "optional_first",
    ]


def test_unclear_response_is_clarified_then_retained_as_unresolved(client):
    _, session = create_screening(client)
    started = start_conversation(client, session["id"], max_attempts=2)
    first = respond(client, session["id"], "unclear", "Maybe, I think it was some time ago.")
    assert first.status_code == 200
    assert first.json()["conversation"]["state"] == "clarification_needed"
    assert first.json()["conversation"]["clarification_attempts"] == 1
    assert first.json()["prompt"]["question_key"] == started["prompt"]["question_key"]

    second = respond(client, session["id"], "unclear", "I cannot give a clearer estimate.")
    assert second.status_code == 200
    assert second.json()["conversation"]["state"] == "incomplete"
    turns = history(client, session["id"])
    assert "Maybe, I think it was some time ago." in [turn["message_text"] for turn in turns]
    assert "I cannot give a clearer estimate." in [turn["message_text"] for turn in turns]
    answers = client.get(f"/api/screening-sessions/{session['id']}/answers").json()
    assert answers[0]["is_missing"] is True
    assert answers[0]["original_response"] is None
    assert answers[0]["normalized_value"] is None
    assert client.get(f"/api/screening-sessions/{session['id']}").json()["status"] == "incomplete"


def test_empty_required_responses_are_bounded_and_optional_empty_is_missing(client):
    questions = [question("required_answer", 0), question("optional_answer", 1, required=False)]
    _, session = create_screening(client, questions=questions)
    start_conversation(client, session["id"], max_attempts=2)
    first = respond(client, session["id"], "no_response")
    assert first.status_code == 200
    assert first.json()["conversation"]["state"] == "clarification_needed"
    second = respond(client, session["id"], "no_response")
    assert second.status_code == 200
    assert second.json()["prompt"]["question_key"] == "optional_answer"
    third = respond(client, session["id"], "no_response")
    assert third.status_code == 200
    assert third.json()["conversation"]["state"] == "incomplete"
    turns = history(client, session["id"])
    assert sum(turn["speaker"] == "candidate" and turn["message_text"] == "" for turn in turns) == 3
    answers = client.get(f"/api/screening-sessions/{session['id']}/answers").json()
    assert {a["question_key"]: a["is_missing"] for a in answers} == {
        "required_answer": True,
        "optional_answer": True,
    }


def test_repeat_and_explicit_clarification_endpoints(client):
    _, session = create_screening(client)
    start = start_conversation(client, session["id"])
    repeated = client.post(f"/api/screening-sessions/{session['id']}/conversation/repeat")
    assert repeated.status_code == 200
    assert repeated.json()["prompt"]["question_key"] == start["prompt"]["question_key"]
    assert history(client, session["id"])[-1]["turn_type"] == "repetition"

    clarification = client.post(f"/api/screening-sessions/{session['id']}/conversation/clarify")
    assert clarification.status_code == 200
    assert clarification.json()["conversation"]["state"] == "clarification_needed"
    response = respond(client, session["id"], "clarification", "I have six years of experience.")
    assert response.status_code == 200
    answers = client.get(f"/api/screening-sessions/{session['id']}/answers").json()
    assert answers[0]["original_response"] == "I have six years of experience."
    assert answers[0]["information_source"] == "explicit"
    assert answers[0]["normalized_value"] is None


def test_candidate_decline_to_answer_continues_but_stop_declines_session(client):
    questions = [question("required_one", 0), question("optional_two", 1, required=False)]
    _, session = create_screening(client, questions=questions)
    start_conversation(client, session["id"])
    refused = respond(client, session["id"], "decline_to_answer", "I prefer not to say.")
    assert refused.status_code == 200
    assert refused.json()["prompt"]["question_key"] == "optional_two"
    skipped = respond(client, session["id"], "skip")
    assert skipped.status_code == 200
    assert skipped.json()["conversation"]["state"] == "incomplete"
    assert client.get(f"/api/screening-sessions/{session['id']}").json()["status"] == "incomplete"

    _, declined_session = create_screening(
        client,
        candidate_overrides={
            "full_name": "Second Simulation Candidate",
            "phone_number": "+91 91234 56780",
            "email": "second-simulation@example.test",
        },
    )
    start_conversation(client, declined_session["id"])
    stopped = respond(client, declined_session["id"], "stop", "I need to stop now.")
    assert stopped.status_code == 200
    assert stopped.json()["conversation"]["state"] == "declined"
    assert client.get(f"/api/screening-sessions/{declined_session['id']}").json()["status"] == "declined"
    assert "I need to stop now." in [turn["message_text"] for turn in history(client, declined_session["id"])]


def test_interruption_resume_and_explicit_end_preserve_history(client):
    _, session = create_screening(client)
    start = start_conversation(client, session["id"])
    interrupted = client.post(f"/api/screening-sessions/{session['id']}/conversation/interrupt")
    assert interrupted.status_code == 200
    assert interrupted.json()["conversation"]["state"] == "interrupted"
    assert client.get(f"/api/screening-sessions/{session['id']}").json()["status"] == "in_progress"
    resumed = start_conversation(client, session["id"])
    assert resumed["outcome"] == "resumed"
    assert resumed["conversation"]["state"] == "awaiting_response"
    assert resumed["prompt"]["question_key"] == start["prompt"]["question_key"]
    assert history(client, session["id"])[-1]["turn_type"] == "repetition"

    ended = client.post(f"/api/screening-sessions/{session['id']}/conversation/end")
    assert ended.status_code == 200
    assert ended.json()["conversation"]["state"] == "incomplete"
    assert client.get(f"/api/screening-sessions/{session['id']}").json()["status"] == "incomplete"
    assert client.get(f"/api/screening-sessions/{session['id']}/answers").json()[0]["is_missing"] is True


def test_invalid_transitions_missing_conversation_and_api_validation(client):
    _, session = create_screening(client)
    no_conversation = client.post(
        f"/api/screening-sessions/{session['id']}/conversation/response",
        json={"question_key": "experience", "disposition": "answer", "response_text": "Six years."},
    )
    assert no_conversation.status_code == 404
    bad_body = client.post(
        f"/api/screening-sessions/{session['id']}/conversation",
        json={"max_clarification_attempts": 0},
    )
    assert bad_body.status_code == 422

    start_conversation(client, session["id"])
    bad_response = respond(client, session["id"], "answer", " ")
    assert bad_response.status_code == 422
    wrong_action = respond(client, session["id"], "clarification", "Six years.")
    assert wrong_action.status_code == 409
    completed = respond(client, session["id"], "answer", "Six years.")
    assert completed.status_code == 200
    duplicate_action = respond(client, session["id"], "answer", "Again six years.")
    assert duplicate_action.status_code == 409
    repeat_after_end = client.post(f"/api/screening-sessions/{session['id']}/conversation/repeat")
    assert repeat_after_end.status_code == 409


def test_stale_response_question_key_cannot_answer_the_next_question(client):
    _, session = create_screening(
        client, questions=[question("first_question", 0), question("second_question", 1)]
    )
    start_conversation(client, session["id"])
    stale = client.post(
        f"/api/screening-sessions/{session['id']}/conversation/response",
        json={
            "question_key": "second_question",
            "disposition": "answer",
            "response_text": "This belongs to the next question.",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "Response question key does not match the active question."


def test_start_missing_session_and_history_turn_order(client):
    missing = client.post(f"/api/screening-sessions/{UUID(int=12345)}/conversation")
    assert missing.status_code == 404

    _, session = create_screening(client)
    start_conversation(client, session["id"])
    respond(client, session["id"], "repeat")
    turns = history(client, session["id"])
    assert [turn["turn_number"] for turn in turns] == list(range(1, len(turns) + 1))


def test_start_finishes_if_required_questions_were_already_answered(client):
    _, session = create_screening(client)
    saved = client.post(
        f"/api/screening-sessions/{session['id']}/answers/experience",
        json={"original_response": "Six years.", "information_source": "explicit"},
    )
    assert saved.status_code == 200
    started = start_conversation(client, session["id"])
    assert started["conversation"]["state"] == "completed"
    assert started["prompt"] is None
    assert client.get(f"/api/screening-sessions/{session['id']}").json()["status"] == "completed"
