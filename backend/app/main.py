from fastapi import FastAPI
from fastapi import HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import engine
from app.routes import router as candidates_router
from app.calls.routes import router as calls_router
from app.screenings.routes import router as screenings_router
from app.conversations.routes import router as conversations_router
from app.calls.bolna_routes import router as bolna_router

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)
app.include_router(candidates_router)
app.include_router(calls_router)
app.include_router(screenings_router)
app.include_router(conversations_router)
app.include_router(bolna_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database", tags=["health"])
def database_health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Database is unavailable.") from exc
    return {"status": "ok"}
