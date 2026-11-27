"""Represent Bolna finalization and retain retrieved screening results.

Revision ID: 0007_bolna_finalization
Revises: 0006_screening_conversations
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_bolna_finalization"
down_revision: Union[str, None] = "0006_screening_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = (
    "queued", "initiated", "ringing", "in_progress", "finalizing", "completed",
    "disconnected", "failed", "no_answer", "busy", "canceled", "reconciliation_required",
)


def _status_constraint() -> str:
    return "status IN (" + ", ".join(f"'{value}'" for value in STATUSES) + ")"


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        "SELECT candidate_id, count(*) AS call_count FROM calls WHERE provider = 'bolna' "
        "GROUP BY candidate_id HAVING count(*) > 1 ORDER BY candidate_id"
    )).all()
    if duplicates:
        identifiers = ", ".join(str(row.candidate_id) for row in duplicates)
        raise RuntimeError(
            "Cannot add Bolna duplicate-call protection; multiple Bolna calls already exist for candidate IDs: "
            + identifiers
        )
    op.drop_constraint("ck_calls_status", "calls", type_="check")
    op.create_check_constraint("ck_calls_status", "calls", _status_constraint())
    op.drop_constraint("ck_call_events_status", "call_events", type_="check")
    op.create_check_constraint("ck_call_events_status", "call_events", _status_constraint())
    op.create_index(
        "uq_calls_one_bolna_per_candidate",
        "calls",
        ["candidate_id"],
        unique=True,
        postgresql_where=sa.text("provider = 'bolna'"),
        sqlite_where=sa.text("provider = 'bolna'"),
    )
    op.add_column("screening_sessions", sa.Column("provider_transcript", sa.Text(), nullable=True))
    op.add_column("screening_sessions", sa.Column("provider_summary", sa.Text(), nullable=True))
    op.add_column("screening_sessions", sa.Column("provider_extracted_data", sa.JSON(), nullable=True))
    op.add_column(
        "screening_sessions", sa.Column("provider_call_duration_seconds", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_screening_sessions_provider_duration",
        "screening_sessions",
        "provider_call_duration_seconds IS NULL OR provider_call_duration_seconds >= 0",
    )


def downgrade() -> None:
    connection = op.get_bind()
    finalizing_calls = connection.scalar(sa.text("SELECT count(*) FROM calls WHERE status = 'finalizing'"))
    finalizing_events = connection.scalar(sa.text("SELECT count(*) FROM call_events WHERE status = 'finalizing'"))
    if finalizing_calls or finalizing_events:
        raise RuntimeError("Cannot downgrade while calls or events use the finalizing status.")
    result_rows = connection.scalar(sa.text(
        "SELECT count(*) FROM screening_sessions WHERE provider_transcript IS NOT NULL "
        "OR provider_summary IS NOT NULL OR provider_extracted_data IS NOT NULL "
        "OR provider_call_duration_seconds IS NOT NULL"
    ))
    if result_rows:
        raise RuntimeError("Cannot downgrade while screening sessions contain retrieved provider results.")

    op.drop_constraint("ck_screening_sessions_provider_duration", "screening_sessions", type_="check")
    op.drop_column("screening_sessions", "provider_call_duration_seconds")
    op.drop_column("screening_sessions", "provider_extracted_data")
    op.drop_column("screening_sessions", "provider_summary")
    op.drop_column("screening_sessions", "provider_transcript")
    op.drop_index("uq_calls_one_bolna_per_candidate", table_name="calls")
    previous = tuple(value for value in STATUSES if value != "finalizing")
    sql = "status IN (" + ", ".join(f"'{value}'" for value in previous) + ")"
    op.drop_constraint("ck_call_events_status", "call_events", type_="check")
    op.create_check_constraint("ck_call_events_status", "call_events", sql)
    op.drop_constraint("ck_calls_status", "calls", type_="check")
    op.create_check_constraint("ck_calls_status", "calls", sql)
