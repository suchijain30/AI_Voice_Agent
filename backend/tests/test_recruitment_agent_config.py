from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Candidate, ScreeningAnswer, ScreeningSession
from app.recruitment_agent.builder import (
    RecruitmentAgentConfigurationBuilder,
    RecruitmentCandidateNotFound,
    RecruitmentContextConflict,
    RecruitmentScreeningSessionNotFound,
)
from app.recruitment_agent.mock import MockAgentConfigurationConsumer
from app.recruitment_agent.schemas import RecruitmentAgentConfiguration, ScreeningAgentContext
from app.recruitment_agent.service import RecruitmentAgentPreparationService


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_candidate(db: Session, **overrides) -> Candidate:
    values = {
        "full_name": "Synthetic Candidate",
        "phone_number": "+91 98765 43210",
        "normalized_phone_number": "+919876543210",
        "email": None,
        "job_title": "Backend Engineer",
        "normalized_job_title": "backend engineer",
        "job_description": "Build reliable API services.",
        "years_of_experience": 4.5,
        "skills": ["Python", "FastAPI"],
        "location": "Pune",
    } | overrides
    candidate = Candidate(**values)
    db.add(candidate)
    db.commit()
    return candidate


def make_session(db: Session, candidate: Candidate) -> ScreeningSession:
    session = ScreeningSession(
        candidate_id=candidate.id,
        status="created",
        question_config=[
            {"question_key": "notice_period", "question_text": "What is your notice period?", "required": True,
             "order": 1, "category": "availability", "follow_up_guidance": "Clarify the number of days if needed."},
            {"question_key": "role_interest", "question_text": "Are you interested in this role?", "required": False,
             "order": 0, "category": "interest", "follow_up_guidance": None},
        ],
    )
    db.add(session)
    db.commit()
    return session


def test_builder_assembles_candidate_job_and_ordered_question_context(db_session):
    candidate = make_candidate(db_session, email="synthetic@example.test")
    screening = make_session(db_session, candidate)

    configuration = RecruitmentAgentConfigurationBuilder(db_session).build(candidate.id, screening.id)

    assert configuration.candidate.application_id == candidate.id
    assert configuration.candidate.name == candidate.full_name
    assert configuration.candidate.phone_number is None
    assert configuration.candidate.email is None
    assert configuration.candidate.stated_experience_years == 4.5
    assert configuration.job.title == candidate.job_title
    assert configuration.job.description == candidate.job_description
    assert [question.question_key for question in configuration.screening.questions] == [
        "role_interest", "notice_period"
    ]
    assert configuration.screening.questions[0].required is False
    assert configuration.screening.questions[1].required is True
    assert configuration.screening.questions[1].follow_up_guidance
    assert configuration.instructions.persona == "AI recruitment assistant"
    assert "unknown" in configuration.instructions.extraction_rules
    assert configuration.instructions.language_options == ["English", "Hindi", "Hinglish"]


def test_builder_preserves_existing_answers_and_provenance(db_session):
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    db_session.add_all([
        ScreeningAnswer(session_id=screening.id, question_key="role_interest", original_response="Yes, interested",
                        normalized_value="interested", information_source="explicit", confidence=0.99, is_missing=False),
        ScreeningAnswer(session_id=screening.id, question_key="notice_period", original_response=None,
                        normalized_value=None, information_source=None, confidence=None, is_missing=True),
    ])
    db_session.commit()

    result = RecruitmentAgentConfigurationBuilder(db_session).build(candidate.id, screening.id)

    assert [answer.question_key for answer in result.screening.existing_answers] == ["role_interest", "notice_period"]
    assert result.screening.existing_answers[0].information_source == "explicit"
    assert result.screening.existing_answers[1].is_missing is True


def test_phone_is_included_only_when_explicitly_requested(db_session):
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    builder = RecruitmentAgentConfigurationBuilder(db_session)

    assert builder.build(candidate.id, screening.id).candidate.phone_number is None
    assert builder.build(candidate.id, screening.id, include_phone=True).candidate.phone_number == "+919876543210"


def test_builder_handles_empty_optional_candidate_context(db_session):
    candidate = make_candidate(db_session, email=None, years_of_experience=None, skills=[], location=None)
    screening = make_session(db_session, candidate)

    result = RecruitmentAgentConfigurationBuilder(db_session).build(candidate.id, screening.id)

    assert result.candidate.email is None
    assert result.candidate.stated_experience_years is None
    assert result.candidate.skills == []
    assert result.candidate.location is None


def test_builder_rejects_missing_records_and_mismatched_candidate(db_session):
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    other_candidate = make_candidate(db_session, full_name="Another Synthetic Candidate",
                                     phone_number="+91 91234 56780", normalized_phone_number="+919123456780",
                                     email=None)
    builder = RecruitmentAgentConfigurationBuilder(db_session)

    with pytest.raises(RecruitmentCandidateNotFound):
        builder.build(uuid4(), screening.id)
    with pytest.raises(RecruitmentScreeningSessionNotFound):
        builder.build(candidate.id, uuid4())
    with pytest.raises(RecruitmentContextConflict):
        builder.build(other_candidate.id, screening.id)


def test_configuration_serialization_is_valid_and_contains_no_secrets(db_session):
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    serialized = RecruitmentAgentConfigurationBuilder(db_session).build(candidate.id, screening.id).model_dump(mode="json")
    parsed = RecruitmentAgentConfiguration.model_validate(serialized)

    assert parsed.model_dump(mode="json") == serialized
    assert "api_key" not in str(serialized).lower()
    assert "password" not in str(serialized).lower()


def test_invalid_question_snapshot_and_extra_configuration_fields_are_rejected(db_session):
    with pytest.raises(ValidationError):
        ScreeningAgentContext(session_id=uuid4(), questions=[])
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    serialized = RecruitmentAgentConfigurationBuilder(db_session).build(candidate.id, screening.id).model_dump()
    serialized["provider_api_key"] = "not-allowed"
    with pytest.raises(ValidationError):
        RecruitmentAgentConfiguration.model_validate(serialized)


def test_mock_configuration_consumer_validates_and_retains_isolated_copy(db_session):
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    config = RecruitmentAgentConfigurationBuilder(db_session).build(candidate.id, screening.id)
    consumer = MockAgentConfigurationConsumer()

    consumer.prepare_agent(config)
    retained = consumer.last_configuration
    assert retained == config
    assert retained is not config
    assert retained.candidate.phone_number is None
    assert consumer.name == "mock-agent-configuration"
    assert not hasattr(consumer, "start_call")

    retained.candidate.name = "mutated inspection copy"
    assert consumer.last_configuration.candidate.name == "Synthetic Candidate"


def test_preparation_service_runs_builder_and_mock_consumer_without_calling(db_session):
    candidate = make_candidate(db_session)
    screening = make_session(db_session, candidate)
    consumer = MockAgentConfigurationConsumer()

    prepared = RecruitmentAgentPreparationService(db_session, consumer).prepare(candidate.id, screening.id)

    assert prepared == consumer.last_configuration
    assert db_session.query(ScreeningSession).count() == 1
    assert db_session.query(ScreeningAnswer).count() == 0
