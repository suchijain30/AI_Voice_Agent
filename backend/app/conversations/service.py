from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.conversations.orchestrator import (
    AnswerDraft,
    ConversationSnapshot,
    OrchestrationResult,
    ResponseDisposition,
    ScreeningConversationOrchestrator,
)
from app.conversations.schemas import (
    AgentPromptRead,
    ConversationInteractionRead,
    ConversationRead,
    ConversationTurnRead,
)
from app.conversations.types import ConversationState
from app.models import (
    Candidate,
    ScreeningAnswer,
    ScreeningConversation,
    ScreeningConversationTurn,
    ScreeningSession,
)
from app.screenings.schemas import ScreeningQuestion
from app.screenings.schemas import ScreeningAnswerUpsert
from app.screenings.types import SCREENING_TRANSITIONS, ScreeningSessionStatus


class ConversationError(Exception):
    pass


class ConversationNotFound(ConversationError):
    pass


class ScreeningSessionForConversationNotFound(ConversationError):
    pass


class ConversationConflict(ConversationError):
    pass


class ConversationStorageError(ConversationError):
    pass


@dataclass(frozen=True)
class ConversationInterpretationSource:
    question: ScreeningQuestion
    conversation_state: str
    clarification_attempts: int
    max_clarification_attempts: int
    job_title: str
    job_description: str
    previous_turns: tuple[ConversationTurnRead, ...]


class ConversationService:
    def __init__(self, db: Session, orchestrator: ScreeningConversationOrchestrator | None = None):
        self.db = db
        self.orchestrator = orchestrator or ScreeningConversationOrchestrator()

    def start_or_resume(
        self, screening_session_id: UUID, *, max_clarification_attempts: int = 2
    ) -> ConversationInteractionRead:
        screening_session = self.db.scalar(
            select(ScreeningSession)
            .where(ScreeningSession.id == screening_session_id)
            .with_for_update()
        )
        if screening_session is None:
            raise ScreeningSessionForConversationNotFound("Screening session not found.")
        conversation = self.db.scalar(
            select(ScreeningConversation).where(
                ScreeningConversation.screening_session_id == screening_session_id
            )
        )
        if conversation is None:
            if screening_session.status not in {
                ScreeningSessionStatus.CREATED.value,
                ScreeningSessionStatus.IN_PROGRESS.value,
            }:
                raise ConversationConflict("A terminal screening session cannot start a conversation.")
            conversation = ScreeningConversation(
                screening_session_id=screening_session_id,
                state=ConversationState.READY.value,
                max_clarification_attempts=max_clarification_attempts,
            )
            self.db.add(conversation)
            try:
                self.db.flush()
            except IntegrityError as exc:
                self.db.rollback()
                raise ConversationConflict("A conversation already exists for this screening session.") from exc

        self._assert_state_consistency(conversation, screening_session)
        snapshot = self._snapshot(conversation, screening_session)
        candidate = self.db.get(Candidate, screening_session.candidate_id)
        result = self.orchestrator.start_or_resume(snapshot, candidate.job_title)
        self._apply_result(conversation, screening_session, result)
        self._commit("Could not start or resume simulated conversation.")
        conversation_read = self._conversation_read(conversation, screening_session, candidate)
        return ConversationInteractionRead(
            conversation=conversation_read,
            outcome=result.outcome,
            prompt=conversation_read.current_prompt,
        )

    def get_conversation(self, screening_session_id: UUID) -> ConversationRead:
        conversation, screening_session, candidate = self._get_conversation_bundle(screening_session_id)
        self._assert_state_consistency(conversation, screening_session)
        return self._conversation_read(conversation, screening_session, candidate)

    def get_history(self, screening_session_id: UUID) -> list[ConversationTurnRead]:
        conversation, screening_session, _ = self._get_conversation_bundle(screening_session_id)
        self._assert_state_consistency(conversation, screening_session)
        turns = self.db.scalars(
            select(ScreeningConversationTurn)
            .where(ScreeningConversationTurn.conversation_id == conversation.id)
            .order_by(ScreeningConversationTurn.turn_number)
        ).all()
        return [ConversationTurnRead.model_validate(turn) for turn in turns]

    def get_interpretation_inputs(
        self, screening_session_id: UUID, *, question_key: str
    ) -> ConversationInterpretationSource:
        conversation, session, candidate = self._get_conversation_bundle(screening_session_id)
        self._assert_state_consistency(conversation, session)
        if conversation.state not in {
            ConversationState.AWAITING_RESPONSE.value,
            ConversationState.CLARIFICATION_NEEDED.value,
        } or conversation.current_question_key != question_key:
            raise ConversationConflict("Response question key does not match the active question.")
        question = next(
            (ScreeningQuestion.model_validate(item) for item in session.question_config
             if item.get("question_key") == conversation.current_question_key),
            None,
        )
        if question is None:
            raise ConversationConflict("The active screening question is unavailable.")
        turns = self.get_history(screening_session_id)
        return ConversationInterpretationSource(
            question=question,
            conversation_state=conversation.state,
            clarification_attempts=conversation.clarification_attempts,
            max_clarification_attempts=conversation.max_clarification_attempts,
            job_title=candidate.job_title,
            job_description=candidate.job_description,
            previous_turns=tuple(turns),
        )

    def submit_response(
        self,
        screening_session_id: UUID,
        *,
        question_key: str,
        disposition: ResponseDisposition,
        response_text: str | None,
        answer_details: ScreeningAnswerUpsert | None = None,
    ) -> ConversationInteractionRead:
        conversation, screening_session, candidate = self._get_conversation_bundle(screening_session_id, lock=True)
        self._assert_state_consistency(conversation, screening_session)
        snapshot = self._snapshot(conversation, screening_session)
        if snapshot.current_question_key != question_key:
            raise ConversationConflict("Response question key does not match the active question.")
        result = self.orchestrator.submit_response(
            snapshot,
            candidate.job_title,
            disposition=disposition,
            response_text=response_text,
        )
        if answer_details is not None:
            if result.answer is None or result.answer.is_missing:
                raise ConversationConflict("Interpretation cannot attach an answer to a non-answer disposition.")
            if answer_details.original_response != response_text:
                raise ConversationConflict("Interpreted response does not match the original candidate response.")
            result = replace(
                result,
                answer=replace(
                    result.answer,
                    normalized_value=answer_details.normalized_value,
                    information_source=answer_details.information_source,
                    confidence=answer_details.confidence,
                ),
            )
        return self._apply_and_read(conversation, screening_session, candidate, result)

    def repeat_question(self, screening_session_id: UUID) -> ConversationInteractionRead:
        conversation, screening_session, candidate = self._get_conversation_bundle(screening_session_id, lock=True)
        self._assert_state_consistency(conversation, screening_session)
        result = self.orchestrator.repeat_question(
            self._snapshot(conversation, screening_session), candidate.job_title
        )
        return self._apply_and_read(conversation, screening_session, candidate, result)

    def request_clarification(self, screening_session_id: UUID) -> ConversationInteractionRead:
        conversation, screening_session, candidate = self._get_conversation_bundle(screening_session_id, lock=True)
        self._assert_state_consistency(conversation, screening_session)
        result = self.orchestrator.request_clarification(
            self._snapshot(conversation, screening_session), candidate.job_title
        )
        return self._apply_and_read(conversation, screening_session, candidate, result)

    def interrupt(self, screening_session_id: UUID) -> ConversationInteractionRead:
        conversation, screening_session, candidate = self._get_conversation_bundle(screening_session_id, lock=True)
        self._assert_state_consistency(conversation, screening_session)
        result = self.orchestrator.interrupt(self._snapshot(conversation, screening_session))
        return self._apply_and_read(conversation, screening_session, candidate, result)

    def end(self, screening_session_id: UUID) -> ConversationInteractionRead:
        conversation, screening_session, candidate = self._get_conversation_bundle(screening_session_id, lock=True)
        self._assert_state_consistency(conversation, screening_session)
        result = self.orchestrator.end(self._snapshot(conversation, screening_session))
        return self._apply_and_read(conversation, screening_session, candidate, result)

    def _apply_and_read(
        self,
        conversation: ScreeningConversation,
        screening_session: ScreeningSession,
        candidate: Candidate,
        result: OrchestrationResult,
    ) -> ConversationInteractionRead:
        self._apply_result(conversation, screening_session, result)
        self._commit("Could not update simulated conversation.")
        return ConversationInteractionRead(
            conversation=self._conversation_read(conversation, screening_session, candidate),
            outcome=result.outcome,
            prompt=self._prompt_read(result.prompt),
        )

    def _apply_result(
        self,
        conversation: ScreeningConversation,
        screening_session: ScreeningSession,
        result: OrchestrationResult,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._transition_screening_session(screening_session, result.screening_status, now)
        conversation.state = result.state.value
        conversation.current_question_key = result.current_question_key
        conversation.clarification_attempts = result.clarification_attempts
        if result.state in {
            ConversationState.COMPLETED,
            ConversationState.DECLINED,
            ConversationState.INCOMPLETE,
        }:
            conversation.ended_at = conversation.ended_at or now
        if result.answer is not None:
            self._save_answer(screening_session.id, result.answer)

        last_turn = self.db.scalar(
            select(func.max(ScreeningConversationTurn.turn_number)).where(
                ScreeningConversationTurn.conversation_id == conversation.id
            )
        ) or 0
        for offset, turn in enumerate(result.turns, start=1):
            self.db.add(
                ScreeningConversationTurn(
                    conversation_id=conversation.id,
                    turn_number=last_turn + offset,
                    speaker=turn.speaker.value,
                    message_text=turn.message_text,
                    question_key=turn.question_key,
                    turn_type=turn.turn_type.value,
                )
            )

    def _save_answer(self, session_id: UUID, draft: AnswerDraft) -> None:
        answer = self.db.scalar(
            select(ScreeningAnswer).where(
                ScreeningAnswer.session_id == session_id,
                ScreeningAnswer.question_key == draft.question_key,
            )
        )
        if answer is None:
            answer = ScreeningAnswer(session_id=session_id, question_key=draft.question_key)
            self.db.add(answer)
        answer.original_response = draft.original_response
        answer.normalized_value = draft.normalized_value
        answer.information_source = draft.information_source or ("explicit" if not draft.is_missing else None)
        answer.confidence = draft.confidence
        answer.is_missing = draft.is_missing

    @staticmethod
    def _transition_screening_session(
        session: ScreeningSession, next_status: ScreeningSessionStatus, now: datetime
    ) -> None:
        current = ScreeningSessionStatus(session.status)
        if current != next_status:
            allowed = SCREENING_TRANSITIONS.get(current, set())
            if next_status not in allowed:
                # Starting can finish immediately if the screening already has
                # all answers, but the legal path still passes through in_progress.
                if not (
                    current == ScreeningSessionStatus.CREATED
                    and next_status in {ScreeningSessionStatus.COMPLETED, ScreeningSessionStatus.INCOMPLETE}
                ):
                    raise ConversationConflict(
                        f"Screening session cannot transition from {current.value} to {next_status.value}."
                    )
                session.status = ScreeningSessionStatus.IN_PROGRESS.value
                session.started_at = session.started_at or now
            session.status = next_status.value
        if next_status == ScreeningSessionStatus.IN_PROGRESS and session.started_at is None:
            session.started_at = now
        if next_status in {
            ScreeningSessionStatus.COMPLETED,
            ScreeningSessionStatus.DECLINED,
            ScreeningSessionStatus.DISCONNECTED,
            ScreeningSessionStatus.INCOMPLETE,
        }:
            session.ended_at = session.ended_at or now

    def _snapshot(
        self, conversation: ScreeningConversation, session: ScreeningSession
    ) -> ConversationSnapshot:
        answer_rows = self.db.scalars(
            select(ScreeningAnswer).where(ScreeningAnswer.session_id == session.id)
        ).all()
        return ConversationSnapshot(
            state=ConversationState(conversation.state),
            screening_status=ScreeningSessionStatus(session.status),
            questions=tuple(ScreeningQuestion.model_validate(item) for item in session.question_config),
            answers={answer.question_key: answer.is_missing for answer in answer_rows},
            current_question_key=conversation.current_question_key,
            clarification_attempts=conversation.clarification_attempts,
            max_clarification_attempts=conversation.max_clarification_attempts,
        )

    def _conversation_read(
        self,
        conversation: ScreeningConversation,
        session: ScreeningSession,
        candidate: Candidate,
    ) -> ConversationRead:
        snapshot = self._snapshot(conversation, session)
        prompt = None
        if conversation.state in {
            ConversationState.AWAITING_RESPONSE.value,
            ConversationState.CLARIFICATION_NEEDED.value,
        }:
            prompt = self.orchestrator.current_prompt(snapshot, candidate.job_title)
            last_agent_turn = self.db.scalar(
                select(ScreeningConversationTurn)
                .where(
                    ScreeningConversationTurn.conversation_id == conversation.id,
                    ScreeningConversationTurn.question_key == conversation.current_question_key,
                    ScreeningConversationTurn.speaker == "agent",
                )
                .order_by(ScreeningConversationTurn.turn_number.desc())
            )
            if prompt is not None and last_agent_turn is not None:
                prompt = replace(prompt, spoken_wording=last_agent_turn.message_text)
        return ConversationRead(
            id=conversation.id,
            screening_session_id=session.id,
            state=ConversationState(conversation.state),
            current_question_key=conversation.current_question_key,
            clarification_attempts=conversation.clarification_attempts,
            max_clarification_attempts=conversation.max_clarification_attempts,
            current_prompt=self._prompt_read(prompt),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            ended_at=conversation.ended_at,
        )

    @staticmethod
    def _prompt_read(prompt) -> AgentPromptRead | None:
        return AgentPromptRead.model_validate(prompt.__dict__) if prompt is not None else None

    def _get_conversation_bundle(
        self, screening_session_id: UUID, *, lock: bool = False
    ) -> tuple[ScreeningConversation, ScreeningSession, Candidate]:
        session_query = select(ScreeningSession).where(ScreeningSession.id == screening_session_id)
        if lock:
            session_query = session_query.with_for_update()
        screening_session = self.db.scalar(session_query)
        if screening_session is None:
            raise ScreeningSessionForConversationNotFound("Screening session not found.")
        query = select(ScreeningConversation).where(
            ScreeningConversation.screening_session_id == screening_session_id
        )
        if lock:
            query = query.with_for_update()
        conversation = self.db.scalar(query)
        if conversation is None:
            raise ConversationNotFound("Conversation has not been started for this screening session.")
        candidate = self.db.get(Candidate, screening_session.candidate_id)
        return conversation, screening_session, candidate

    def _assert_state_consistency(
        self, conversation: ScreeningConversation, session: ScreeningSession
    ) -> None:
        state = ConversationState(conversation.state)
        screening_status = ScreeningSessionStatus(session.status)
        expected = {
            ConversationState.READY: {ScreeningSessionStatus.CREATED, ScreeningSessionStatus.IN_PROGRESS},
            ConversationState.AWAITING_RESPONSE: {ScreeningSessionStatus.IN_PROGRESS},
            ConversationState.CLARIFICATION_NEEDED: {ScreeningSessionStatus.IN_PROGRESS},
            ConversationState.INTERRUPTED: {ScreeningSessionStatus.IN_PROGRESS},
            ConversationState.COMPLETED: {ScreeningSessionStatus.COMPLETED},
            ConversationState.DECLINED: {ScreeningSessionStatus.DECLINED},
            ConversationState.INCOMPLETE: {ScreeningSessionStatus.INCOMPLETE},
        }
        if screening_status not in expected[state]:
            raise ConversationConflict("Conversation state does not match the screening session status.")

    def _commit(self, message: str) -> None:
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ConversationStorageError(message) from exc
