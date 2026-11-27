"""Add provider-agnostic call lifecycle records.

Revision ID: 0003_call_lifecycle
Revises: 0002_duplicate_apps
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_call_lifecycle"
down_revision = "0002_duplicate_apps"
branch_labels = None
depends_on = None

CALL_STATUSES = (
    "queued",
    "initiated",
    "ringing",
    "in_progress",
    "completed",
    "failed",
    "no_answer",
    "busy",
    "canceled",
)
STATUS_SQL = ", ".join(f"'{status}'" for status in CALL_STATUSES)


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_call_id", sa.String(length=200), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("configuration_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({STATUS_SQL})", name="ck_calls_status"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_calls_idempotency_key"),
        sa.UniqueConstraint("provider", "provider_call_id", name="uq_calls_provider_call_id"),
    )
    op.create_index("ix_calls_candidate_id", "calls", ["candidate_id"], unique=False)

    op.create_table(
        "call_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN ({STATUS_SQL})", name="ck_call_events_status"),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_call_events_provider_event_id"),
    )
    op.create_index("ix_call_events_call_id", "call_events", ["call_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_call_events_call_id", table_name="call_events")
    op.drop_table("call_events")
    op.drop_index("ix_calls_candidate_id", table_name="calls")
    op.drop_table("calls")
