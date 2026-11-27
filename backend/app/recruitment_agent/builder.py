from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, ScreeningAnswer, ScreeningSession
from app.recruitment_agent.schemas import (
    CandidateAgentContext,
    CandidateAnswerContext,
    JobAgentContext,
    RecruitmentAgentConfiguration,
    ScreeningAgentContext,
)
from app.screenings.schemas import ScreeningQuestion


class RecruitmentAgentConfigurationError(Exception):
    """Base configuration preparation error."""


class RecruitmentCandidateNotFound(RecruitmentAgentConfigurationError):
    pass


class RecruitmentScreeningSessionNotFound(RecruitmentAgentConfigurationError):
    pass


class RecruitmentContextConflict(RecruitmentAgentConfigurationError):
    pass


class RecruitmentAgentConfigurationBuilder:
    """Build deterministic provider-neutral context from existing application records."""

    def __init__(self, db: Session):
        self.db = db

    def build(
        self,
        candidate_id: UUID,
        session_id: UUID,
        *,
        include_phone: bool = False,
    ) -> RecruitmentAgentConfiguration:
        candidate = self.db.get(Candidate, candidate_id)
        if candidate is None:
            raise RecruitmentCandidateNotFound("Candidate not found.")
        session = self.db.get(ScreeningSession, session_id)
        if session is None:
            raise RecruitmentScreeningSessionNotFound("Screening session not found.")
        if session.candidate_id != candidate.id:
            raise RecruitmentContextConflict("The screening session belongs to a different candidate.")

        questions = sorted(
            (ScreeningQuestion.model_validate(item) for item in session.question_config),
            key=lambda question: question.order,
        )
        answers = self.db.scalars(
            select(ScreeningAnswer).where(ScreeningAnswer.session_id == session.id)
        ).all()
        order = {question.question_key: question.order for question in questions}
        answers = sorted(answers, key=lambda item: (order.get(item.question_key, 10_000), item.question_key))

        candidate_context = CandidateAgentContext(
            application_id=candidate.id,
            name=candidate.full_name,
            phone_number=candidate.normalized_phone_number if include_phone else None,
            # Email is not required for the voice conversation; keep it out of
            # the prepared context to minimize candidate data exposure.
            email=None,
            stated_experience_years=float(candidate.years_of_experience) if candidate.years_of_experience is not None else None,
            skills=list(candidate.skills or []),
            location=candidate.location,
        )
        return RecruitmentAgentConfiguration(
            candidate=candidate_context,
            job=JobAgentContext(
                title=candidate.job_title,
                description=candidate.job_description,
                candidate_listed_skills=list(candidate.skills or []),
                candidate_location=candidate.location,
            ),
            screening=ScreeningAgentContext(
                session_id=session.id,
                questions=questions,
                existing_answers=[
                    CandidateAnswerContext(
                        question_key=answer.question_key,
                        original_response=answer.original_response,
                        normalized_value=answer.normalized_value,
                        information_source=answer.information_source,
                        is_missing=answer.is_missing,
                    )
                    for answer in answers
                ],
            ),
        )
