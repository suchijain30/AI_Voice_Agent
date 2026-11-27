from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    Integer,
    String,
    Text,
    text,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.calls.types import CALL_STATUSES
from app.screenings.types import SCREENING_SESSION_STATUSES
from app.conversations.types import CONVERSATION_STATES, TURN_SPEAKERS, TURN_TYPES


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint(
            "normalized_phone_number",
            "normalized_job_title",
            name="uq_candidates_phone_job_title_normalized",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    normalized_phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_job_title: Mapped[str] = mapped_column(String(600), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    years_of_experience: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    calls: Mapped[list["Call"]] = relationship(back_populates="candidate")


_status_sql = ", ".join(f"'{status}'" for status in CALL_STATUSES)


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_calls_idempotency_key"),
        UniqueConstraint("provider", "provider_call_id", name="uq_calls_provider_call_id"),
        Index(
            "uq_calls_one_bolna_per_candidate",
            "candidate_id",
            unique=True,
            sqlite_where=text("provider = 'bolna'"),
            postgresql_where=text("provider = 'bolna'"),
        ),
        CheckConstraint(f"status IN ({_status_sql})", name="ck_calls_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    configuration_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate: Mapped[Candidate] = relationship(back_populates="calls")
    events: Mapped[list["CallEvent"]] = relationship(back_populates="call", cascade="all, delete-orphan")

    @property
    def provider_outcome(self) -> str | None:
        return (self.configuration_metadata or {}).get("provider_outcome")


class CallEvent(Base):
    __tablename__ = "call_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_call_events_provider_event_id"),
        CheckConstraint(f"status IN ({_status_sql})", name="ck_call_events_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    call_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    call: Mapped[Call] = relationship(back_populates="events")


_screening_status_sql = ", ".join(f"'{status}'" for status in SCREENING_SESSION_STATUSES)


class ScreeningSession(Base):
    __tablename__ = "screening_sessions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_screening_status_sql})", name="ck_screening_sessions_status"),
        CheckConstraint(
            "provider_call_duration_seconds IS NULL OR provider_call_duration_seconds >= 0",
            name="ck_screening_sessions_provider_duration",
        ),
        UniqueConstraint("call_id", name="uq_screening_sessions_call_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    call_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="created", server_default="created"
    )
    question_config: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_extracted_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    provider_call_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    answers: Mapped[list["ScreeningAnswer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ScreeningAnswer.question_key"
    )
    evaluation: Mapped["ScreeningEvaluation | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    conversation: Mapped["ScreeningConversation | None"] = relationship(
        back_populates="screening_session", cascade="all, delete-orphan", uselist=False
    )


class ScreeningAnswer(Base):
    __tablename__ = "screening_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "question_key", name="uq_screening_answers_session_question"),
        CheckConstraint(
            "information_source IS NULL OR information_source IN ('explicit', 'inferred')",
            name="ck_screening_answers_source",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_screening_answers_confidence",
        ),
        CheckConstraint(
            "is_missing = false OR (original_response IS NULL AND normalized_value IS NULL "
            "AND information_source IS NULL AND confidence IS NULL)",
            name="ck_screening_answers_missing_value",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_key: Mapped[str] = mapped_column(String(64), nullable=False)
    original_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[object | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    information_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    is_missing: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session: Mapped[ScreeningSession] = relationship(back_populates="answers")


class ScreeningEvaluation(Base):
    __tablename__ = "screening_evaluations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("screening_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    evaluation_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session: Mapped[ScreeningSession] = relationship(back_populates="evaluation")


_conversation_state_sql = ", ".join(f"'{state}'" for state in CONVERSATION_STATES)
_turn_speaker_sql = ", ".join(f"'{speaker}'" for speaker in TURN_SPEAKERS)
_turn_type_sql = ", ".join(f"'{turn_type}'" for turn_type in TURN_TYPES)


class ScreeningConversation(Base):
    __tablename__ = "screening_conversations"
    __table_args__ = (
        CheckConstraint(f"state IN ({_conversation_state_sql})", name="ck_screening_conversations_state"),
        CheckConstraint("clarification_attempts >= 0", name="ck_screening_conversations_attempts"),
        CheckConstraint(
            "max_clarification_attempts >= 1 AND max_clarification_attempts <= 5",
            name="ck_screening_conversations_max_attempts",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    screening_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("screening_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="ready", server_default="ready")
    current_question_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clarification_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    max_clarification_attempts: Mapped[int] = mapped_column(default=2, server_default="2", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    screening_session: Mapped[ScreeningSession] = relationship(back_populates="conversation")
    turns: Mapped[list["ScreeningConversationTurn"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ScreeningConversationTurn.turn_number"
    )


class ScreeningConversationTurn(Base):
    __tablename__ = "screening_conversation_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "turn_number", name="uq_screening_conversation_turn_number"),
        CheckConstraint("turn_number >= 1", name="ck_screening_conversation_turn_number"),
        CheckConstraint(f"speaker IN ({_turn_speaker_sql})", name="ck_screening_conversation_turn_speaker"),
        CheckConstraint(f"turn_type IN ({_turn_type_sql})", name="ck_screening_conversation_turn_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("screening_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_number: Mapped[int] = mapped_column(nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    turn_type: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped[ScreeningConversation] = relationship(back_populates="turns")
