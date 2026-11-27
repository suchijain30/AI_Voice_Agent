from enum import StrEnum


class ConversationState(StrEnum):
    READY = "ready"
    AWAITING_RESPONSE = "awaiting_response"
    CLARIFICATION_NEEDED = "clarification_needed"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    DECLINED = "declined"
    INCOMPLETE = "incomplete"


CONVERSATION_STATES = tuple(state.value for state in ConversationState)


class TurnSpeaker(StrEnum):
    AGENT = "agent"
    CANDIDATE = "candidate"
    SYSTEM = "system"


class TurnType(StrEnum):
    QUESTION = "question"
    RESPONSE = "response"
    CLARIFICATION = "clarification"
    REPETITION = "repetition"
    SYSTEM_EVENT = "system_event"


TURN_SPEAKERS = tuple(speaker.value for speaker in TurnSpeaker)
TURN_TYPES = tuple(turn_type.value for turn_type in TurnType)
