from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Call, Candidate, ScreeningAnswer, ScreeningEvaluation, ScreeningSession
from app.screenings.schemas import (
    ScreeningAnswerRead,
    ScreeningAnswerUpsert,
    ScreeningEvaluationInput,
    ScreeningEvaluationRead,
    ScreeningQuestion,
    ScreeningSessionCreate,
    ScreeningSessionRead,
)
from app.screenings.types import SCREENING_TRANSITIONS, ScreeningSessionStatus


class ScreeningError(Exception):
    pass


class ScreeningCandidateNotFound(ScreeningError):
    pass


class ScreeningCallNotFound(ScreeningError):
    pass


class ScreeningSessionNotFound(ScreeningError):
    pass


class ScreeningConflict(ScreeningError):
    pass


class ScreeningRequiredAnswersMissing(ScreeningConflict):
    pass


class ScreeningInvalidTransition(ScreeningError):
    pass


class ScreeningInvalidQuestion(ScreeningError):
    pass


class ScreeningEvaluationUnavailable(ScreeningError):
    pass


class ScreeningStorageError(ScreeningError):
    pass


class ScreeningService:
    def __init__(self, db: Session):
        self.db = db

    def create_session(
        self,
        payload: ScreeningSessionCreate,
        default_questions: list[ScreeningQuestion],
    ) -> ScreeningSessionRead:
        candidate = self.db.get(Candidate, payload.candidate_id)
        if candidate is None:
            raise ScreeningCandidateNotFound("Candidate not found.")
        if payload.call_id is not None:
            call = self.db.get(Call, payload.call_id)
            if call is None:
                raise ScreeningCallNotFound("Call not found.")
            if call.candidate_id != candidate.id:
                raise ScreeningConflict("The call belongs to a different candidate.")

        selected_questions = sorted(payload.questions or default_questions, key=lambda question: question.order)
        session = ScreeningSession(
            candidate_id=candidate.id,
            call_id=payload.call_id,
            status=ScreeningSessionStatus.CREATED.value,
            question_config=[question.model_dump(mode="json") for question in selected_questions],
        )
        self.db.add(session)
        try:
            self.db.commit()
            self.db.refresh(session)
        except IntegrityError as exc:
            self.db.rollback()
            raise ScreeningConflict("A screening session already exists for this call.") from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ScreeningStorageError("Could not create screening session.") from exc
        return self._session_read(session)

    def get_session(self, session_id: UUID) -> ScreeningSessionRead:
        return self._session_read(self._get_session_model(session_id))

    def list_sessions_for_candidate(self, candidate_id: UUID) -> list[ScreeningSessionRead]:
        if self.db.get(Candidate, candidate_id) is None:
            raise ScreeningCandidateNotFound("Candidate not found.")
        sessions = list(
            self.db.scalars(
                select(ScreeningSession)
                .where(ScreeningSession.candidate_id == candidate_id)
                .order_by(ScreeningSession.created_at.desc())
            ).all()
        )
        return [self._session_read(item) for item in sessions]

    def update_status(self, session_id: UUID, next_status: ScreeningSessionStatus) -> ScreeningSessionRead:
        session = self._get_session_model(session_id)
        current = ScreeningSessionStatus(session.status)
        if next_status == current:
            return self._session_read(session)
        if next_status not in SCREENING_TRANSITIONS.get(current, set()):
            raise ScreeningInvalidTransition(
                f"Screening session cannot transition from {current.value} to {next_status.value}."
            )
        if next_status == ScreeningSessionStatus.COMPLETED:
            required_keys = {
                item["question_key"] for item in session.question_config if item["required"]
            }
            recorded_keys = set(
                self.db.scalars(
                    select(ScreeningAnswer.question_key).where(
                        ScreeningAnswer.session_id == session_id,
                        ScreeningAnswer.is_missing.is_(False),
                    )
                ).all()
            )
            missing_keys = sorted(required_keys - recorded_keys)
            if missing_keys:
                raise ScreeningRequiredAnswersMissing(
                    "Required screening answers are missing or unanswered: " + ", ".join(missing_keys)
                )

        now = datetime.now(timezone.utc)
        session.status = next_status.value
        if next_status == ScreeningSessionStatus.IN_PROGRESS and session.started_at is None:
            session.started_at = now
        if next_status in {
            ScreeningSessionStatus.COMPLETED,
            ScreeningSessionStatus.DECLINED,
            ScreeningSessionStatus.DISCONNECTED,
            ScreeningSessionStatus.INCOMPLETE,
        }:
            session.ended_at = now
        self._commit("Could not update screening session status.")
        return self._session_read(session)

    def save_answer(
        self, session_id: UUID, question_key: str, payload: ScreeningAnswerUpsert
    ) -> ScreeningAnswerRead:
        session = self._get_session_model(session_id)
        if session.status not in {ScreeningSessionStatus.CREATED.value, ScreeningSessionStatus.IN_PROGRESS.value}:
            raise ScreeningConflict("Answers cannot be changed after the screening session has ended.")
        if question_key not in {item["question_key"] for item in session.question_config}:
            raise ScreeningInvalidQuestion("Question key is not configured for this screening session.")

        answer = self.db.scalar(
            select(ScreeningAnswer).where(
                ScreeningAnswer.session_id == session_id,
                ScreeningAnswer.question_key == question_key,
            )
        )
        if answer is None:
            answer = ScreeningAnswer(session_id=session_id, question_key=question_key)
            self.db.add(answer)
        answer.original_response = payload.original_response
        answer.normalized_value = payload.normalized_value
        answer.information_source = payload.information_source
        answer.confidence = payload.confidence
        answer.is_missing = payload.is_missing
        self._commit("Could not save screening answer.")
        self.db.refresh(answer)
        return ScreeningAnswerRead.model_validate(answer)

    def list_answers(self, session_id: UUID) -> list[ScreeningAnswerRead]:
        session = self._get_session_model(session_id)
        answers = list(
            self.db.scalars(select(ScreeningAnswer).where(ScreeningAnswer.session_id == session_id)).all()
        )
        order = {item["question_key"]: item["order"] for item in session.question_config}
        answers.sort(key=lambda answer: (order.get(answer.question_key, 10_000), answer.question_key))
        return [ScreeningAnswerRead.model_validate(answer) for answer in answers]

    def save_evaluation(
        self, session_id: UUID, payload: ScreeningEvaluationInput
    ) -> ScreeningEvaluationRead:
        session = self._get_session_model(session_id)
        if session.status in {ScreeningSessionStatus.CREATED.value, ScreeningSessionStatus.IN_PROGRESS.value}:
            raise ScreeningEvaluationUnavailable("Evaluation is available only after screening has ended.")
        candidate = self.db.get(Candidate, session.candidate_id)
        evaluation = self.db.scalar(
            select(ScreeningEvaluation).where(ScreeningEvaluation.session_id == session_id)
        )
        if evaluation is None:
            evaluation = ScreeningEvaluation(session_id=session_id, evaluation_data={})
            self.db.add(evaluation)
        evaluation.evaluation_data = payload.model_dump(mode="json")
        self._commit("Could not save screening evaluation.")
        self.db.refresh(evaluation)
        return self._evaluation_read(evaluation, candidate)

    def get_evaluation(self, session_id: UUID) -> ScreeningEvaluationRead:
        session = self._get_session_model(session_id)
        evaluation = self.db.scalar(
            select(ScreeningEvaluation).where(ScreeningEvaluation.session_id == session_id)
        )
        if evaluation is None:
            raise ScreeningEvaluationUnavailable("Screening evaluation has not been created.")
        candidate = self.db.get(Candidate, session.candidate_id)
        return self._evaluation_read(evaluation, candidate)

    def _get_session_model(self, session_id: UUID) -> ScreeningSession:
        session = self.db.get(ScreeningSession, session_id)
        if session is None:
            raise ScreeningSessionNotFound("Screening session not found.")
        return session

    @staticmethod
    def _session_read(session: ScreeningSession) -> ScreeningSessionRead:
        return ScreeningSessionRead(
            id=session.id,
            candidate_id=session.candidate_id,
            call_id=session.call_id,
            status=ScreeningSessionStatus(session.status),
            questions=[ScreeningQuestion.model_validate(question) for question in session.question_config],
            created_at=session.created_at,
            updated_at=session.updated_at,
            started_at=session.started_at,
            ended_at=session.ended_at,
            provider_transcript=session.provider_transcript,
            provider_summary=session.provider_summary,
            provider_extracted_data=session.provider_extracted_data,
            provider_call_duration_seconds=session.provider_call_duration_seconds,
        )

    @staticmethod
    def _evaluation_read(evaluation: ScreeningEvaluation, candidate: Candidate) -> ScreeningEvaluationRead:
        validated_data = ScreeningEvaluationInput.model_validate(evaluation.evaluation_data)
        return ScreeningEvaluationRead(
            **validated_data.model_dump(),
            id=evaluation.id,
            session_id=evaluation.session_id,
            candidate_name=candidate.full_name,
            job_title=candidate.job_title,
            created_at=evaluation.created_at,
            updated_at=evaluation.updated_at,
        )

    def _commit(self, message: str) -> None:
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ScreeningStorageError(message) from exc
