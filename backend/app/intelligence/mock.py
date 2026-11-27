from collections.abc import Mapping
from typing import Any

from app.conversations.orchestrator import ResponseDisposition
from app.conversations.types import ConversationState
from app.intelligence.errors import IntelligenceProviderFailure, IntelligenceTimeout
from app.intelligence.schemas import InterpretationContext, ResponseInterpretation


class MockIntelligenceProvider:
    """Explicit-fixture mock. It never examines arbitrary response semantics."""

    def __init__(self, scenario: str, *, fixtures: Mapping[str, dict[str, Any]] | None = None):
        self.scenario = scenario
        self.fixtures = dict(fixtures or {})

    def interpret(self, context: InterpretationContext) -> ResponseInterpretation:
        if self.scenario == "timeout":
            raise IntelligenceTimeout("Synthetic mock interpretation timeout.")
        if self.scenario == "provider_failure":
            raise IntelligenceProviderFailure("Synthetic mock interpretation failure.")
        if self.scenario == "unsupported_classification":
            return ResponseInterpretation.model_validate(
                {
                    "original_response": context.raw_response,
                    "disposition": "unsupported",
                    "question_key": context.question_key,
                }
            )
        if self.scenario == "invalid_confidence":
            return ResponseInterpretation.model_validate(
                self._base(context)
                | {
                    "disposition": ResponseDisposition.ANSWER.value,
                    "information_source": "explicit",
                    "confidence": 1.5,
                }
            )
        if self.scenario == "wrong_question_key":
            data = self._interpretation_data(context, "clear_answer")
            data["question_key"] = "other_question"
            return ResponseInterpretation.model_validate(data)
        if self.scenario == "invalid_output":
            return ResponseInterpretation.model_validate({"original_response": context.raw_response})

        configured = self.fixtures.get(self.scenario)
        if configured is not None:
            data = self._base(context) | configured
        else:
            data = self._interpretation_data(context, self.scenario)
        return ResponseInterpretation.model_validate(data)

    def _base(self, context: InterpretationContext) -> dict[str, Any]:
        return {
            "original_response": context.raw_response,
            "question_key": context.question_key,
            "confidence": None,
            "metadata": {"fixture": self.scenario},
        }

    def _interpretation_data(self, context: InterpretationContext, scenario: str) -> dict[str, Any]:
        base = self._base(context)
        if scenario == "clear_answer":
            disposition = (
                ResponseDisposition.CLARIFICATION
                if context.conversation_state == ConversationState.CLARIFICATION_NEEDED.value
                else ResponseDisposition.ANSWER
            )
            return base | {
                "disposition": disposition.value,
                "clarification_needed": False,
                "information_source": "explicit",
                "is_missing": False,
            }
        if scenario == "experience_five_years_example":
            if (
                context.question_category != "experience"
                or context.raw_response != "I started working in 2021, so around five years."
            ):
                raise IntelligenceProviderFailure("The fixed experience example does not match this test input.")
            disposition = (
                ResponseDisposition.CLARIFICATION
                if context.conversation_state == ConversationState.CLARIFICATION_NEEDED.value
                else ResponseDisposition.ANSWER
            )
            return base | {
                "disposition": disposition.value,
                "extracted_answer": "approximately five years",
                "normalized_answer": {"value": 5, "unit": "years", "approximate": True},
                "clarification_needed": False,
                "confidence": 0.88,
                "information_source": "explicit",
                "is_missing": False,
                "metadata": {"fixture": "fixed_example_output_not_natural_language_inference"},
            }
        if scenario in {"unclear", "clarification_requested"}:
            return base | {
                "disposition": ResponseDisposition.UNCLEAR.value,
                "clarification_needed": True,
                "clarification_reason": "The explicitly selected mock scenario requires clarification.",
                "is_missing": True,
            }
        if scenario == "no_answer":
            return base | {
                "disposition": ResponseDisposition.NO_RESPONSE.value,
                "clarification_needed": False,
                "is_missing": True,
            }
        if scenario == "question_repeat_requested":
            return base | {
                "disposition": ResponseDisposition.REPEAT.value,
                "clarification_needed": False,
                "is_missing": True,
            }
        if scenario == "candidate_declined":
            return base | {
                "disposition": ResponseDisposition.DECLINE_TO_ANSWER.value,
                "clarification_needed": False,
                "is_missing": True,
            }
        if scenario == "candidate_wants_to_stop":
            return base | {
                "disposition": ResponseDisposition.STOP.value,
                "clarification_needed": False,
                "is_missing": True,
            }
        raise IntelligenceProviderFailure("Unknown deterministic mock scenario.")
