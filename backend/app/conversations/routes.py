from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.conversations.orchestrator import InvalidConversationAction
from app.conversations.schemas import (
    CandidateResponseRequest,
    ConversationInteractionRead,
    ConversationRead,
    ConversationStartRequest,
    ConversationTurnRead,
)
from app.conversations.service import (
    ConversationConflict,
    ConversationNotFound,
    ConversationService,
    ConversationStorageError,
    ScreeningSessionForConversationNotFound,
)
from app.database import get_db
from app.config import IntelligenceSettings
from app.intelligence.workflow import IntelligenceWorkflowService

router = APIRouter(tags=["simulated-conversations"])


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    return ConversationService(db)


@router.post(
    "/api/screening-sessions/{screening_session_id}/conversation",
    response_model=ConversationInteractionRead,
)
def start_or_resume_conversation(
    screening_session_id: UUID,
    payload: ConversationStartRequest | None = None,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationInteractionRead:
    try:
        return service.start_or_resume(
            screening_session_id,
            max_clarification_attempts=payload.max_clarification_attempts if payload else 2,
        )
    except ScreeningSessionForConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationConflict, InvalidConversationAction) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/api/screening-sessions/{screening_session_id}/conversation",
    response_model=ConversationRead,
)
def get_conversation(
    screening_session_id: UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRead:
    try:
        return service.get_conversation(screening_session_id)
    except (ConversationNotFound, ScreeningSessionForConversationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/api/screening-sessions/{screening_session_id}/conversation/turns",
    response_model=list[ConversationTurnRead],
)
def get_conversation_history(
    screening_session_id: UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationTurnRead]:
    try:
        return service.get_history(screening_session_id)
    except (ConversationNotFound, ScreeningSessionForConversationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{screening_session_id}/conversation/response",
    response_model=ConversationInteractionRead,
)
def submit_simulated_response(
    screening_session_id: UUID,
    payload: CandidateResponseRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationInteractionRead:
    try:
        if payload.intelligence_scenario is not None:
            settings = IntelligenceSettings()
            if settings.intelligence_provider != "mock":
                raise HTTPException(status_code=503, detail="Only the offline mock intelligence provider is available.")
            result = IntelligenceWorkflowService(service, settings).interpret_and_submit(
                screening_session_id,
                question_key=payload.question_key,
                raw_response=payload.response_text,
                scenario=payload.intelligence_scenario,
            )
            return result.interaction.model_copy(
                update={
                    "interpretation": result.interpretation.model_dump(mode="json"),
                    "used_safe_fallback": result.used_safe_fallback,
                    "fallback_reason": result.fallback_reason,
                }
            )
        return service.submit_response(
            screening_session_id,
            question_key=payload.question_key,
            disposition=payload.disposition,
            response_text=payload.response_text,
        )
    except ScreeningSessionForConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationConflict, InvalidConversationAction) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{screening_session_id}/conversation/repeat",
    response_model=ConversationInteractionRead,
)
def repeat_current_question(
    screening_session_id: UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationInteractionRead:
    try:
        return service.repeat_question(screening_session_id)
    except (ConversationNotFound, ScreeningSessionForConversationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationConflict, InvalidConversationAction) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{screening_session_id}/conversation/clarify",
    response_model=ConversationInteractionRead,
)
def request_clarification(
    screening_session_id: UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationInteractionRead:
    try:
        return service.request_clarification(screening_session_id)
    except (ConversationNotFound, ScreeningSessionForConversationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationConflict, InvalidConversationAction) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{screening_session_id}/conversation/interrupt",
    response_model=ConversationInteractionRead,
)
def interrupt_simulated_conversation(
    screening_session_id: UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationInteractionRead:
    try:
        return service.interrupt(screening_session_id)
    except (ConversationNotFound, ScreeningSessionForConversationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationConflict, InvalidConversationAction) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{screening_session_id}/conversation/end",
    response_model=ConversationInteractionRead,
)
def end_simulated_conversation(
    screening_session_id: UUID,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationInteractionRead:
    try:
        return service.end(screening_session_id)
    except (ConversationNotFound, ScreeningSessionForConversationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationConflict, InvalidConversationAction) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
