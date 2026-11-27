from dataclasses import dataclass
from uuid import UUID

from app.config import IntelligenceSettings
from app.conversations.orchestrator import ResponseDisposition
from app.conversations.schemas import ConversationInteractionRead
from app.conversations.service import ConversationService
from app.intelligence.context import InterpretationContextBuilder
from app.intelligence.mock import MockIntelligenceProvider
from app.intelligence.provider import ResponseInterpreter
from app.intelligence.schemas import ResponseInterpretation
from app.screenings.schemas import ScreeningAnswerUpsert


@dataclass(frozen=True)
class IntelligenceWorkflowResult:
    interaction: ConversationInteractionRead
    interpretation: ResponseInterpretation
    used_safe_fallback: bool
    fallback_reason: str | None = None


class IntelligenceWorkflowService:
    """Compose interpretation with the deterministic conversation service."""

    def __init__(
        self,
        conversations: ConversationService,
        settings: IntelligenceSettings,
        *,
        interpreter: ResponseInterpreter | None = None,
    ):
        self.conversations = conversations
        self.settings = settings
        self.context_builder = InterpretationContextBuilder(settings)
        self.interpreter = interpreter

    def interpret_and_submit(
        self,
        screening_session_id: UUID,
        *,
        question_key: str,
        raw_response: str | None,
        scenario: str,
    ) -> IntelligenceWorkflowResult:
        source = self.conversations.get_interpretation_inputs(
            screening_session_id, question_key=question_key
        )
        fallback_reason = None
        try:
            context = self.context_builder.build(
                source, question_key=question_key, raw_response=raw_response
            )
            interpreter = self.interpreter or MockIntelligenceProvider(scenario)
            raw_result = interpreter.interpret(context)
            interpretation = ResponseInterpretation.model_validate(raw_result)
            if interpretation.question_key != source.question.question_key:
                raise ValueError("Interpreter changed the active question key.")
            if interpretation.original_response != raw_response:
                raise ValueError("Interpreter changed the original candidate response.")
            if interpretation.disposition == ResponseDisposition.ANSWER and (
                source.conversation_state == "clarification_needed"
            ):
                interpretation = interpretation.model_copy(
                    update={"disposition": ResponseDisposition.CLARIFICATION}
                )
            elif interpretation.disposition == ResponseDisposition.CLARIFICATION and (
                source.conversation_state != "clarification_needed"
            ):
                raise ValueError("Interpreter requested a clarification answer outside clarification state.")
        except Exception:
            interpretation = self._safe_fallback(source.question.question_key, raw_response)
            fallback_reason = "interpretation_unavailable_or_invalid"

        answer_details = None
        if interpretation.disposition in {
            ResponseDisposition.ANSWER,
            ResponseDisposition.CLARIFICATION,
        }:
            answer_details = ScreeningAnswerUpsert(
                original_response=raw_response,
                normalized_value=interpretation.normalized_answer,
                information_source=interpretation.information_source,
                confidence=interpretation.confidence,
                is_missing=False,
            )
        interaction = self.conversations.submit_response(
            screening_session_id,
            question_key=source.question.question_key,
            disposition=interpretation.disposition,
            response_text=raw_response,
            answer_details=answer_details,
        )
        return IntelligenceWorkflowResult(
            interaction=interaction,
            interpretation=interpretation,
            used_safe_fallback=fallback_reason is not None,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _safe_fallback(question_key: str, raw_response: str | None) -> ResponseInterpretation:
        return ResponseInterpretation(
            original_response=raw_response,
            disposition=ResponseDisposition.UNCLEAR,
            question_key=question_key,
            clarification_needed=True,
            clarification_reason="Response interpretation was unavailable; request explicit clarification.",
            is_missing=True,
            metadata={"fallback": "safe_unclear"},
        )
