from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.calls.providers import MockProvider
from app.calls.schemas import CallRead
from app.calls.service import (
    CallExecutionDisabled,
    CallLifecycleService,
    CallNotFound,
    CallStorageError,
    CandidateNotFound,
    IdempotencyConflict,
    ProviderOperationError,
    UnresolvedCallOutcome,
)
from app.database import get_db
from app.config import get_settings

router = APIRouter(tags=["calls"])


def get_call_service(db: Session = Depends(get_db)) -> CallLifecycleService:
    return CallLifecycleService(db, MockProvider(), enabled=get_settings().mock_calls_enabled)


@router.post(
    "/api/candidates/{candidate_id}/calls",
    response_model=CallRead,
    status_code=status.HTTP_201_CREATED,
)
def create_mock_call(
    candidate_id: UUID,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    service: CallLifecycleService = Depends(get_call_service),
) -> CallRead:
    try:
        call, created = service.create_call(candidate_id, idempotency_key)
    except CallExecutionDisabled as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except CandidateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnresolvedCallOutcome as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ProviderOperationError, CallStorageError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return call


@router.get("/api/calls/{call_id}", response_model=CallRead)
def get_call(call_id: UUID, service: CallLifecycleService = Depends(get_call_service)) -> CallRead:
    try:
        return service.get_call(call_id)
    except CallNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
