from typing import Protocol

from app.intelligence.schemas import InterpretationContext, ResponseInterpretation


class ResponseInterpreter(Protocol):
    """Vendor-neutral boundary for interpreting one response in bounded context."""

    def interpret(self, context: InterpretationContext) -> ResponseInterpretation:
        """Return a validated interpretation without changing conversation state."""
