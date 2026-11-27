from enum import StrEnum


class ScreeningSessionStatus(StrEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DECLINED = "declined"
    DISCONNECTED = "disconnected"
    INCOMPLETE = "incomplete"


SCREENING_SESSION_STATUSES = tuple(status.value for status in ScreeningSessionStatus)

SCREENING_TRANSITIONS = {
    ScreeningSessionStatus.CREATED: {
        ScreeningSessionStatus.IN_PROGRESS,
        ScreeningSessionStatus.DECLINED,
        ScreeningSessionStatus.DISCONNECTED,
        ScreeningSessionStatus.INCOMPLETE,
    },
    ScreeningSessionStatus.IN_PROGRESS: {
        ScreeningSessionStatus.COMPLETED,
        ScreeningSessionStatus.DECLINED,
        ScreeningSessionStatus.DISCONNECTED,
        ScreeningSessionStatus.INCOMPLETE,
    },
    ScreeningSessionStatus.DISCONNECTED: {ScreeningSessionStatus.INCOMPLETE},
}
