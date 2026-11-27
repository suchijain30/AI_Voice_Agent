from app.config import IntelligenceSettings
from app.conversations.service import ConversationInterpretationSource
from app.intelligence.errors import IntelligenceContextError
from app.intelligence.schemas import InterpretationContext, InterpretationTurn


class InterpretationContextBuilder:
    """Build a bounded, provider-neutral context from only the active screening turn."""

    def __init__(self, settings: IntelligenceSettings):
        self.settings = settings

    def build(
        self,
        source: ConversationInterpretationSource,
        *,
        question_key: str,
        raw_response: str | None,
    ) -> InterpretationContext:
        if question_key != source.question.question_key:
            raise IntelligenceContextError("Response question key does not match the active screening question.")
        if raw_response is not None and len(raw_response) > self.settings.intelligence_max_response_chars:
            raise IntelligenceContextError("Candidate response exceeds the configured interpretation size limit.")

        description = source.job_description[:2000]
        response_size = len(raw_response or "")
        fixed_size = (
            response_size
            + len(source.question.question_text)
            + len(source.question.follow_up_guidance or "")
            + len(source.question.question_key)
            + len(source.question.category)
            + len(source.job_title)
            + len(description)
        )
        if fixed_size > self.settings.intelligence_max_context_chars:
            remaining = self.settings.intelligence_max_context_chars - (
                response_size
                + len(source.question.question_text)
                + len(source.question.follow_up_guidance or "")
                + len(source.question.question_key)
                + len(source.question.category)
                + len(source.job_title)
            )
            if remaining < 0:
                raise IntelligenceContextError("Current response and question exceed the configured context limit.")
            description = description[:remaining]
            fixed_size = self.settings.intelligence_max_context_chars

        remaining = self.settings.intelligence_max_context_chars - fixed_size
        selected_turns: list[InterpretationTurn] = []
        recent_turns = (
            source.previous_turns[-self.settings.intelligence_max_context_turns :]
            if self.settings.intelligence_max_context_turns
            else ()
        )
        for turn in reversed(recent_turns):
            cost = len(turn.message_text) + len(turn.speaker) + len(turn.question_key or "") + len(turn.turn_type)
            if cost > remaining:
                continue
            selected_turns.append(
                InterpretationTurn(
                    speaker=turn.speaker,
                    message_text=turn.message_text,
                    question_key=turn.question_key,
                    turn_type=turn.turn_type,
                )
            )
            remaining -= cost
        selected_turns.reverse()

        try:
            return InterpretationContext(
                question_key=source.question.question_key,
                question_text=source.question.question_text,
                question_follow_up_guidance=source.question.follow_up_guidance,
                question_category=source.question.category,
                question_required=source.question.required,
                raw_response=raw_response,
                job_title=source.job_title,
                job_description_context=description or None,
                previous_turns=selected_turns,
                conversation_state=source.conversation_state,
                clarification_attempt_count=source.clarification_attempts,
                max_clarification_attempts=source.max_clarification_attempts,
            )
        except ValueError as exc:
            raise IntelligenceContextError("Could not construct a valid bounded interpretation context.") from exc
