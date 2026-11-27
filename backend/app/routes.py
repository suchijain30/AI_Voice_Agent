from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Candidate
from app.normalization import normalize_job_title, normalize_phone_number
from app.schemas import CandidateCreate, CandidateRead

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
DUPLICATE_CONSTRAINT = "uq_candidates_phone_job_title_normalized"
DUPLICATE_MESSAGE = "An application from this phone number already exists for this job."


def _is_duplicate_application_violation(exc: IntegrityError) -> bool:
    original = exc.orig
    constraint_name = getattr(getattr(original, "diag", None), "constraint_name", None)
    if constraint_name == DUPLICATE_CONSTRAINT:
        return True
    # SQLite does not expose named constraint diagnostics; keep its test behavior precise.
    return "UNIQUE constraint failed: candidates.normalized_phone_number, candidates.normalized_job_title" in str(original)


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)) -> Candidate:
    normalized_phone = normalize_phone_number(payload.phone_number)
    normalized_title = normalize_job_title(payload.job_title)
    try:
        duplicate_id = db.scalar(
            select(Candidate.id)
            .where(
                Candidate.normalized_phone_number == normalized_phone,
                Candidate.normalized_job_title == normalized_title,
            )
            .limit(1)
        )
        if duplicate_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_MESSAGE)

        candidate = Candidate(
            **payload.model_dump(),
            normalized_phone_number=normalized_phone,
            normalized_job_title=normalized_title,
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
    except HTTPException:
        raise
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_application_violation(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_MESSAGE) from exc
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Candidate storage is temporarily unavailable.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Candidate storage is temporarily unavailable.") from exc
    return candidate


@router.get("", response_model=list[CandidateRead])
def list_candidates(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Candidate]:
    statement = select(Candidate).order_by(Candidate.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(statement).all())


@router.get("/{candidate_id}", response_model=CandidateRead)
def get_candidate(candidate_id: UUID, db: Session = Depends(get_db)) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    return candidate
