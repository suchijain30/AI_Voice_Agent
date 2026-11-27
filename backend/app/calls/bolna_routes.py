from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.calls.bolna import BolnaAdapter
from app.calls.bolna_sync import BolnaSyncService
from app.calls.providers import ProviderDisabled, ProviderRetrievalError
from app.calls.schemas import BolnaSyncRead, CallRead
from app.calls.service import (
    CallExecutionDisabled,
    CallLifecycleService,
    CallNotFound,
    CallStorageError,
    CandidateNotFound,
    IdempotencyConflict,
    InvalidCallTransition,
    ProviderOperationError,
    UnresolvedCallOutcome,
)
from app.config import BolnaSettings
from app.database import get_db
from app.models import ScreeningSession
from app.recruitment_agent.builder import (
    RecruitmentAgentConfigurationBuilder,
    RecruitmentAgentConfigurationError,
    RecruitmentCandidateNotFound,
    RecruitmentContextConflict,
    RecruitmentScreeningSessionNotFound,
)

router = APIRouter(tags=["Bolna integration"])


def get_enabled_bolna_adapter():
    settings = BolnaSettings()
    if not settings.bolna_calls_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bolna integration is disabled by configuration.",
        )
    try:
        adapter = BolnaAdapter.from_settings(settings)
    except ProviderDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        yield adapter
    finally:
        adapter.close()


@router.post(
    "/api/screening-sessions/{session_id}/bolna-call",
    response_model=CallRead,
    status_code=status.HTTP_201_CREATED,
)
def create_bolna_screening_call(
    session_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    adapter: BolnaAdapter = Depends(get_enabled_bolna_adapter),
) -> CallRead:
    session = db.get(ScreeningSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Screening session not found.")
    try:
        configuration = RecruitmentAgentConfigurationBuilder(db).build(
            session.candidate_id, session.id, include_phone=False
        )
        lifecycle = CallLifecycleService(db, adapter, enabled=True)
        call, created = lifecycle.create_call(
            session.candidate_id,
            f"bolna-screening-{session.id}",
            screening_session_id=session.id,
            agent_configuration=configuration,
        )
    except (RecruitmentAgentConfigurationError, RecruitmentCandidateNotFound, RecruitmentScreeningSessionNotFound, RecruitmentContextConflict) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CallExecutionDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (CandidateNotFound, CallNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (IdempotencyConflict, UnresolvedCallOutcome, InvalidCallTransition) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ProviderOperationError, CallStorageError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not created:
        # Session-scoped deterministic idempotency ensures a replay returns the
        # stored local record and cannot create another provider execution.
        response.status_code = status.HTTP_200_OK
    return call


@router.post("/api/calls/{call_id}/bolna-sync", response_model=BolnaSyncRead)
def sync_bolna_execution(
    call_id: UUID,
    db: Session = Depends(get_db),
    adapter: BolnaAdapter = Depends(get_enabled_bolna_adapter),
) -> BolnaSyncRead:
    try:
        call, result_available = BolnaSyncService(db, adapter).sync_call(call_id)
        return BolnaSyncRead(call=call, result_available=result_available)
    except CallNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProviderRetrievalError, InvalidCallTransition) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CallStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/calls/bolna-finalizing/stale", response_model=list[CallRead])
def list_stale_bolna_calls(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[CallRead]:
    """Read-only worklist; an operator explicitly triggers sync per call."""
    settings = BolnaSettings()
    return BolnaSyncService.list_stale_finalizing_calls(
        db,
        stale_after_seconds=settings.bolna_finalizing_timeout_seconds,
        limit=limit,
    )
