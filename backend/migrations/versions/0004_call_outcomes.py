"""Represent disconnected and unresolved provider call outcomes.

Revision ID: 0004_call_outcomes
Revises: 0003_call_lifecycle
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_call_outcomes"
down_revision = "0003_call_lifecycle"
branch_labels = None
depends_on = None

CALL_STATUSES = (
    "queued",
    "initiated",
    "ringing",
    "in_progress",
    "completed",
    "disconnected",
    "failed",
    "no_answer",
    "busy",
    "canceled",
    "reconciliation_required",
)
PREVIOUS_STATUSES = tuple(status for status in CALL_STATUSES if status not in {"disconnected", "reconciliation_required"})


def _constraint_sql(statuses: tuple[str, ...]) -> str:
    values = ", ".join(f"'{status}'" for status in statuses)
    return f"status IN ({values})"


def upgrade() -> None:
    op.drop_constraint("ck_calls_status", "calls", type_="check")
    op.create_check_constraint("ck_calls_status", "calls", _constraint_sql(CALL_STATUSES))
    op.drop_constraint("ck_call_events_status", "call_events", type_="check")
    op.create_check_constraint("ck_call_events_status", "call_events", _constraint_sql(CALL_STATUSES))
    op.alter_column(
        "calls", "status", existing_type=sa.String(length=16), type_=sa.String(length=32),
        existing_nullable=False, existing_server_default="queued"
    )
    op.alter_column(
        "call_events", "status", existing_type=sa.String(length=16), type_=sa.String(length=32),
        existing_nullable=False
    )


def downgrade() -> None:
    connection = op.get_bind()
    new_statuses = ("disconnected", "reconciliation_required")
    placeholders = ", ".join(f":status_{index}" for index in range(len(new_statuses)))
    params = {f"status_{index}": value for index, value in enumerate(new_statuses)}
    for table in ("calls", "call_events"):
        count = connection.scalar(
            sa.text(f"SELECT count(*) FROM {table} WHERE status IN ({placeholders})"), params
        )
        if count:
            raise RuntimeError(
                f"Cannot downgrade call outcomes: {table} contains statuses introduced by this revision."
            )

    op.drop_constraint("ck_call_events_status", "call_events", type_="check")
    op.create_check_constraint("ck_call_events_status", "call_events", _constraint_sql(PREVIOUS_STATUSES))
    op.drop_constraint("ck_calls_status", "calls", type_="check")
    op.create_check_constraint("ck_calls_status", "calls", _constraint_sql(PREVIOUS_STATUSES))
    op.alter_column(
        "calls", "status", existing_type=sa.String(length=32), type_=sa.String(length=16),
        existing_nullable=False, existing_server_default="queued"
    )
    op.alter_column(
        "call_events", "status", existing_type=sa.String(length=32), type_=sa.String(length=16),
        existing_nullable=False
    )
