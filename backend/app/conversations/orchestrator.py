"""Pure deterministic conversation flow; no database, provider, or transport code."""

from dataclasses import dataclass
from enum import StrEnum

from app.screenings.schemas import ScreeningQuestion
from app.screenings.types import ScreeningSessionStatus
from app.conversations.types import ConversationState, TurnSpeaker, TurnType


class ResponseDisposition(StrEnum):
    ANSWER = "answer"
    UNCLEAR = "unclear"
    NO_RESPONSE = "no_response"
    DECLINE_TO_ANSWER = "decline_to_answer"
    SKIP = "skip"
    STOP = "stop"
    REPEAT = "repeat"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class ConversationSnapshot:
    state: ConversationState
    screening_status: ScreeningSessionStatus
    questions: tuple[ScreeningQuestion, ...]
    answers: dict[str, bool]
    current_question_key: str | None
    clarification_attempts: int
    max_clarification_attempts: int


@dataclass(frozen=True)
class Prompt:
    question_key: str
    question_text: str
    spoken_wording: str
    follow_up_guidance: str | None
    required: bool
    question_index: int
    total_questions: int


@dataclass(frozen=True)
class TurnDraft:
    speaker: TurnSpeaker
    message_text: str
    question_key: str | None
    turn_type: TurnType


@dataclass(frozen=True)
class AnswerDraft:
    question_key: str
    original_response: str | None
    is_missing: bool
    normalized_value: object | None = None
    information_source: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class OrchestrationResult:
    state: ConversationState
    screening_status: ScreeningSessionStatus
    current_question_key: str | None
    clarification_attempts: int
    prompt: Prompt | None
    turns: tuple[TurnDraft, ...] = ()
    answer: AnswerDraft | None = None
    outcome: str = "awaiting_response"


class InvalidConversationAction(Exception):
    pass


class ScreeningConversationOrchestrator:
    """Advance a simulated screening using explicit caller-supplied dispositions."""

    @staticmethod
    def start_or_resume(snapshot: ConversationSnapshot, job_title: str) -> OrchestrationResult:
        if snapshot.state in {
            ConversationState.COMPLETED,
            ConversationState.DECLINED,
            ConversationState.INCOMPLETE,
        }:
            return ScreeningConversationOrchestrator._unchanged(snapshot, "conversation_ended")

        if snapshot.state == ConversationState.INTERRUPTED:
            question = ScreeningConversationOrchestrator._current_question(snapshot)
            if question is None:
                return ScreeningConversationOrchestrator._advance(snapshot, job_title, {}, ())
            prompt = ScreeningConversationOrchestrator._prompt(snapshot, question, job_title, "repeat")
            return OrchestrationResult(
                state=ConversationState.AWAITING_RESPONSE,
                screening_status=ScreeningSessionStatus.IN_PROGRESS,
                current_question_key=question.question_key,
                clarification_attempts=snapshot.clarification_attempts,
                prompt=prompt,
                turns=(TurnDraft(TurnSpeaker.AGENT, prompt.spoken_wording, question.question_key, TurnType.REPETITION),),
                outcome="resumed",
            )

        if snapshot.state in {ConversationState.AWAITING_RESPONSE, ConversationState.CLARIFICATION_NEEDED}:
            question = ScreeningConversationOrchestrator._current_question(snapshot)
            return OrchestrationResult(
                state=snapshot.state,
                screening_status=ScreeningSessionStatus.IN_PROGRESS,
                current_question_key=snapshot.current_question_key,
                clarification_attempts=snapshot.clarification_attempts,
                prompt=(
                    ScreeningConversationOrchestrator._prompt(
                        snapshot,
                        question,
                        job_title,
                        "clarification" if snapshot.state == ConversationState.CLARIFICATION_NEEDED else "normal",
                    )
                    if question
                    else None
                ),
                outcome="resumed",
            )

        if snapshot.screening_status not in {
            ScreeningSessionStatus.CREATED,
            ScreeningSessionStatus.IN_PROGRESS,
        }:
            raise InvalidConversationAction("A terminal screening session cannot be started or resumed.")
        return ScreeningConversationOrchestrator._advance(
            snapshot, job_title, {}, (), initial=True
        )

    @staticmethod
    def submit_response(
        snapshot: ConversationSnapshot,
        job_title: str,
        *,
        disposition: ResponseDisposition,
        response_text: str | None,
    ) -> OrchestrationResult:
        if snapshot.state not in {ConversationState.AWAITING_RESPONSE, ConversationState.CLARIFICATION_NEEDED}:
            raise InvalidConversationAction("The conversation is not waiting for a candidate response.")
        question = ScreeningConversationOrchestrator._current_question(snapshot)
        if question is None:
            raise InvalidConversationAction("There is no active screening question.")

        candidate_turn = TurnDraft(
            TurnSpeaker.CANDIDATE,
            response_text or "",
            question.question_key,
            TurnType.RESPONSE,
        )
        if disposition == ResponseDisposition.REPEAT:
            prompt = ScreeningConversationOrchestrator._prompt(snapshot, question, job_title, "repeat")
            return OrchestrationResult(
                state=snapshot.state,
                screening_status=ScreeningSessionStatus.IN_PROGRESS,
                current_question_key=question.question_key,
                clarification_attempts=snapshot.clarification_attempts,
                prompt=prompt,
                turns=(candidate_turn, TurnDraft(TurnSpeaker.AGENT, prompt.spoken_wording, question.question_key, TurnType.REPETITION)),
                outcome="question_repeated",
            )

        if disposition == ResponseDisposition.STOP:
            return OrchestrationResult(
                state=ConversationState.DECLINED,
                screening_status=ScreeningSessionStatus.DECLINED,
                current_question_key=None,
                clarification_attempts=0,
                prompt=None,
                turns=(candidate_turn, TurnDraft(
                    TurnSpeaker.AGENT,
                    "Understood. Thank you for your time. We will end the screening here.",
                    question.question_key,
                    TurnType.SYSTEM_EVENT,
                )),
                answer=AnswerDraft(question.question_key, None, True),
                outcome="candidate_ended",
            )

        if disposition in {ResponseDisposition.SKIP, ResponseDisposition.DECLINE_TO_ANSWER}:
            return ScreeningConversationOrchestrator._advance(
                snapshot,
                job_title,
                {question.question_key: True},
                (candidate_turn,),
                answer=AnswerDraft(question.question_key, None, True),
                outcome="question_skipped",
            )

        if disposition == ResponseDisposition.ANSWER:
            if snapshot.state == ConversationState.CLARIFICATION_NEEDED:
                raise InvalidConversationAction("Submit a clarification response while clarification is requested.")
            return ScreeningConversationOrchestrator._advance(
                snapshot,
                job_title,
                {question.question_key: False},
                (candidate_turn,),
                answer=AnswerDraft(question.question_key, response_text, False),
                outcome="answer_recorded",
            )

        if disposition == ResponseDisposition.CLARIFICATION:
            if snapshot.state != ConversationState.CLARIFICATION_NEEDED:
                raise InvalidConversationAction("No clarification is currently requested.")
            return ScreeningConversationOrchestrator._advance(
                snapshot,
                job_title,
                {question.question_key: False},
                (candidate_turn,),
                answer=AnswerDraft(question.question_key, response_text, False),
                outcome="clarification_recorded",
            )

        if disposition in {ResponseDisposition.UNCLEAR, ResponseDisposition.NO_RESPONSE}:
            if disposition == ResponseDisposition.NO_RESPONSE and not question.required:
                return ScreeningConversationOrchestrator._advance(
                    snapshot,
                    job_title,
                    {question.question_key: True},
                    (candidate_turn,),
                    answer=AnswerDraft(question.question_key, None, True),
                    outcome="optional_question_unanswered",
                )
            attempts = snapshot.clarification_attempts + 1
            if attempts >= snapshot.max_clarification_attempts:
                ending = TurnDraft(
                    TurnSpeaker.AGENT,
                    "Thank you. I will leave that question unanswered and continue.",
                    question.question_key,
                    TurnType.SYSTEM_EVENT,
                )
                return ScreeningConversationOrchestrator._advance(
                    snapshot,
                    job_title,
                    {question.question_key: True},
                    (candidate_turn, ending),
                    answer=AnswerDraft(question.question_key, None, True),
                    outcome="clarification_limit_reached",
                )
            prompt = ScreeningConversationOrchestrator._prompt(snapshot, question, job_title, "clarification")
            return OrchestrationResult(
                state=ConversationState.CLARIFICATION_NEEDED,
                screening_status=ScreeningSessionStatus.IN_PROGRESS,
                current_question_key=question.question_key,
                clarification_attempts=attempts,
                prompt=prompt,
                turns=(candidate_turn, TurnDraft(
                    TurnSpeaker.AGENT, prompt.spoken_wording, question.question_key, TurnType.CLARIFICATION
                )),
                outcome="clarification_requested",
            )

        raise InvalidConversationAction("Unsupported response disposition.")

    @staticmethod
    def repeat_question(snapshot: ConversationSnapshot, job_title: str) -> OrchestrationResult:
        if snapshot.state not in {ConversationState.AWAITING_RESPONSE, ConversationState.CLARIFICATION_NEEDED}:
            raise InvalidConversationAction("The active question cannot be repeated in this conversation state.")
        question = ScreeningConversationOrchestrator._current_question(snapshot)
        if question is None:
            raise InvalidConversationAction("There is no active screening question.")
        prompt = ScreeningConversationOrchestrator._prompt(snapshot, question, job_title, "repeat")
        return OrchestrationResult(
            state=snapshot.state,
            screening_status=ScreeningSessionStatus.IN_PROGRESS,
            current_question_key=question.question_key,
            clarification_attempts=snapshot.clarification_attempts,
            prompt=prompt,
            turns=(TurnDraft(TurnSpeaker.AGENT, prompt.spoken_wording, question.question_key, TurnType.REPETITION),),
            outcome="question_repeated",
        )

    @staticmethod
    def request_clarification(snapshot: ConversationSnapshot, job_title: str) -> OrchestrationResult:
        if snapshot.state not in {ConversationState.AWAITING_RESPONSE, ConversationState.CLARIFICATION_NEEDED}:
            raise InvalidConversationAction("Clarification cannot be requested in this conversation state.")
        question = ScreeningConversationOrchestrator._current_question(snapshot)
        if question is None:
            raise InvalidConversationAction("There is no active screening question.")
        attempts = snapshot.clarification_attempts + 1
        if attempts >= snapshot.max_clarification_attempts:
            return ScreeningConversationOrchestrator._advance(
                snapshot,
                job_title,
                {question.question_key: True},
                (TurnDraft(
                    TurnSpeaker.AGENT,
                    "I will leave that question unanswered and continue.",
                    question.question_key,
                    TurnType.SYSTEM_EVENT,
                ),),
                answer=AnswerDraft(question.question_key, None, True),
                outcome="clarification_limit_reached",
            )
        prompt = ScreeningConversationOrchestrator._prompt(snapshot, question, job_title, "clarification")
        return OrchestrationResult(
            state=ConversationState.CLARIFICATION_NEEDED,
            screening_status=ScreeningSessionStatus.IN_PROGRESS,
            current_question_key=question.question_key,
            clarification_attempts=attempts,
            prompt=prompt,
            turns=(TurnDraft(TurnSpeaker.AGENT, prompt.spoken_wording, question.question_key, TurnType.CLARIFICATION),),
            outcome="clarification_requested",
        )

    @staticmethod
    def interrupt(snapshot: ConversationSnapshot) -> OrchestrationResult:
        if snapshot.state not in {ConversationState.AWAITING_RESPONSE, ConversationState.CLARIFICATION_NEEDED}:
            raise InvalidConversationAction("Only an active simulated conversation can be interrupted.")
        return OrchestrationResult(
            state=ConversationState.INTERRUPTED,
            screening_status=ScreeningSessionStatus.IN_PROGRESS,
            current_question_key=snapshot.current_question_key,
            clarification_attempts=snapshot.clarification_attempts,
            prompt=None,
            turns=(TurnDraft(TurnSpeaker.SYSTEM, "Conversation paused for simulation.", snapshot.current_question_key, TurnType.SYSTEM_EVENT),),
            outcome="interrupted",
        )

    @staticmethod
    def end(snapshot: ConversationSnapshot) -> OrchestrationResult:
        if snapshot.state in {ConversationState.COMPLETED, ConversationState.DECLINED, ConversationState.INCOMPLETE}:
            raise InvalidConversationAction("The conversation has already ended.")
        question = ScreeningConversationOrchestrator._current_question(snapshot)
        answer = AnswerDraft(question.question_key, None, True) if question else None
        return OrchestrationResult(
            state=ConversationState.INCOMPLETE,
            screening_status=ScreeningSessionStatus.INCOMPLETE,
            current_question_key=None,
            clarification_attempts=0,
            prompt=None,
            turns=(TurnDraft(TurnSpeaker.AGENT, "Thank you for your time. We will end this screening as incomplete.",
                             question.question_key if question else None, TurnType.SYSTEM_EVENT),),
            answer=answer,
            outcome="ended_incomplete",
        )

    @staticmethod
    def _advance(
        snapshot: ConversationSnapshot,
        job_title: str,
        answer_updates: dict[str, bool],
        turns: tuple[TurnDraft, ...],
        *,
        answer: AnswerDraft | None = None,
        outcome: str = "answer_recorded",
        initial: bool = False,
    ) -> OrchestrationResult:
        answers = dict(snapshot.answers)
        answers.update(answer_updates)
        next_question = ScreeningConversationOrchestrator._next_question(snapshot.questions, answers)
        if next_question is None:
            required_missing = any(
                question.required and answers.get(question.question_key) is True
                for question in snapshot.questions
            )
            state = ConversationState.INCOMPLETE if required_missing else ConversationState.COMPLETED
            session_status = ScreeningSessionStatus.INCOMPLETE if required_missing else ScreeningSessionStatus.COMPLETED
            closing_text = (
                "Thank you for your time. We have finished the screening, with some required information left unanswered."
                if required_missing
                else "Thank you for your time. That completes the screening conversation."
            )
            return OrchestrationResult(
                state=state,
                screening_status=session_status,
                current_question_key=None,
                clarification_attempts=0,
                prompt=None,
                turns=turns + (TurnDraft(TurnSpeaker.AGENT, closing_text, None, TurnType.SYSTEM_EVENT),),
                answer=answer,
                outcome="screening_incomplete" if required_missing else "screening_completed",
            )

        prompt = ScreeningConversationOrchestrator._prompt(
            snapshot, next_question, job_title, "normal", initial=initial
        )
        next_turns = turns + (TurnDraft(TurnSpeaker.AGENT, prompt.spoken_wording, next_question.question_key, TurnType.QUESTION),)
        return OrchestrationResult(
            state=ConversationState.AWAITING_RESPONSE,
            screening_status=ScreeningSessionStatus.IN_PROGRESS,
            current_question_key=next_question.question_key,
            clarification_attempts=0,
            prompt=prompt,
            turns=next_turns,
            answer=answer,
            outcome=outcome,
        )

    @staticmethod
    def _next_question(
        questions: tuple[ScreeningQuestion, ...], answers: dict[str, bool]
    ) -> ScreeningQuestion | None:
        ordered = sorted(questions, key=lambda question: question.order)
        return next(
            (question for question in ordered if question.required and question.question_key not in answers),
            None,
        ) or next(
            (question for question in ordered if question.question_key not in answers),
            None,
        )

    @staticmethod
    def _current_question(snapshot: ConversationSnapshot) -> ScreeningQuestion | None:
        return next(
            (question for question in snapshot.questions if question.question_key == snapshot.current_question_key),
            None,
        )

    @staticmethod
    def _prompt(
        snapshot: ConversationSnapshot,
        question: ScreeningQuestion,
        job_title: str,
        mode: str,
        *,
        initial: bool = False,
    ) -> Prompt:
        ordered = sorted(snapshot.questions, key=lambda item: item.order)
        position = next(index for index, item in enumerate(ordered, start=1) if item.question_key == question.question_key)
        if mode == "clarification":
            wording = f"Could you clarify that a little more? {question.question_text}"
        elif mode == "repeat":
            wording = f"Of course. {question.question_text}"
        elif initial:
            wording = (
                f"Hello, I'm the AI recruitment assistant calling about the {job_title} role. "
                f"{question.question_text}"
            )
        else:
            wording = f"Thank you. {question.question_text}"
        return Prompt(
            question_key=question.question_key,
            question_text=question.question_text,
            spoken_wording=wording,
            follow_up_guidance=question.follow_up_guidance,
            required=question.required,
            question_index=position,
            total_questions=len(ordered),
        )

    @staticmethod
    def current_prompt(snapshot: ConversationSnapshot, job_title: str) -> Prompt | None:
        question = ScreeningConversationOrchestrator._current_question(snapshot)
        if question is None:
            return None
        mode = "clarification" if snapshot.state == ConversationState.CLARIFICATION_NEEDED else "normal"
        return ScreeningConversationOrchestrator._prompt(snapshot, question, job_title, mode)

    @staticmethod
    def _unchanged(snapshot: ConversationSnapshot, outcome: str) -> OrchestrationResult:
        return OrchestrationResult(
            state=snapshot.state,
            screening_status=snapshot.screening_status,
            current_question_key=snapshot.current_question_key,
            clarification_attempts=snapshot.clarification_attempts,
            prompt=None,
            outcome=outcome,
        )
