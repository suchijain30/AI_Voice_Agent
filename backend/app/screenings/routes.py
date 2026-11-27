from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.screenings.questions import INITIAL_SCREENING_QUESTIONS
from app.screenings.schemas import (
    ScreeningAnswerRead,
    ScreeningAnswerUpsert,
    ScreeningEvaluationInput,
    ScreeningEvaluationRead,
    ScreeningSessionCreate,
    ScreeningSessionRead,
    ScreeningSessionStatusUpdate,
)
from app.screenings.service import (
    ScreeningCallNotFound,
    ScreeningCandidateNotFound,
    ScreeningConflict,
    ScreeningEvaluationUnavailable,
    ScreeningInvalidQuestion,
    ScreeningInvalidTransition,
    ScreeningService,
    ScreeningSessionNotFound,
    ScreeningStorageError,
)

router = APIRouter(tags=["screenings"])


def get_screening_service(db: Session = Depends(get_db)) -> ScreeningService:
    return ScreeningService(db)


@router.post(
    "/api/screening-sessions",
    response_model=ScreeningSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_screening_session(
    payload: ScreeningSessionCreate,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningSessionRead:
    try:
        return service.create_session(payload, INITIAL_SCREENING_QUESTIONS)
    except ScreeningCandidateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScreeningCallNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScreeningConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScreeningStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/screening-sessions/{session_id}", response_model=ScreeningSessionRead)
def get_screening_session(
    session_id: UUID,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningSessionRead:
    try:
        return service.get_session(session_id)
    except ScreeningSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/screening-sessions/{session_id}/status", response_model=ScreeningSessionRead)
def update_screening_status(
    session_id: UUID,
    payload: ScreeningSessionStatusUpdate,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningSessionRead:
    try:
        return service.update_status(session_id, payload.status)
    except ScreeningSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScreeningInvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScreeningConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScreeningStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{session_id}/answers/{question_key}",
    response_model=ScreeningAnswerRead,
)
def save_screening_answer(
    session_id: UUID,
    question_key: str,
    payload: ScreeningAnswerUpsert,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningAnswerRead:
    try:
        return service.save_answer(session_id, question_key, payload)
    except ScreeningSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScreeningInvalidQuestion as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScreeningConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScreeningStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/api/screening-sessions/{session_id}/answers",
    response_model=list[ScreeningAnswerRead],
)
def list_screening_answers(
    session_id: UUID,
    service: ScreeningService = Depends(get_screening_service),
) -> list[ScreeningAnswerRead]:
    try:
        return service.list_answers(session_id)
    except ScreeningSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/screening-sessions/{session_id}/evaluation",
    response_model=ScreeningEvaluationRead,
    status_code=status.HTTP_200_OK,
)
def save_screening_evaluation(
    session_id: UUID,
    payload: ScreeningEvaluationInput,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningEvaluationRead:
    try:
        return service.save_evaluation(session_id, payload)
    except ScreeningSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScreeningEvaluationUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScreeningStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/api/screening-sessions/{session_id}/evaluation",
    response_model=ScreeningEvaluationRead,
)
def get_screening_evaluation(
    session_id: UUID,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningEvaluationRead:
    try:
        return service.get_evaluation(session_id)
    except ScreeningSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScreeningEvaluationUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
