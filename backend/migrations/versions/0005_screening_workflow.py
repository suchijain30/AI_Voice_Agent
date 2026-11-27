"""Add provider-neutral recruitment screening sessions, answers and evaluation."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_screening_workflow"
down_revision: Union[str, None] = "0004_call_outcomes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screening_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="created", nullable=False),
        sa.Column("question_config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('created', 'in_progress', 'completed', 'declined', 'disconnected', 'incomplete')",
            name="ck_screening_sessions_status",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_id", name="uq_screening_sessions_call_id"),
    )
    op.create_index("ix_screening_sessions_candidate_id", "screening_sessions", ["candidate_id"])

    op.create_table(
        "screening_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("original_response", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("information_source", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("is_missing", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "information_source IS NULL OR information_source IN ('explicit', 'inferred')",
            name="ck_screening_answers_source",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_screening_answers_confidence",
        ),
        sa.CheckConstraint(
            "is_missing = false OR (original_response IS NULL AND normalized_value IS NULL "
            "AND information_source IS NULL AND confidence IS NULL)",
            name="ck_screening_answers_missing_value",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["screening_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "question_key", name="uq_screening_answers_session_question"),
    )
    op.create_index("ix_screening_answers_session_id", "screening_answers", ["session_id"])

    op.create_table(
        "screening_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["screening_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_screening_evaluations_session_id", "screening_evaluations", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_screening_evaluations_session_id", table_name="screening_evaluations")
    op.drop_table("screening_evaluations")
    op.drop_index("ix_screening_answers_session_id", table_name="screening_answers")
    op.drop_table("screening_answers")
    op.drop_index("ix_screening_sessions_candidate_id", table_name="screening_sessions")
    op.drop_table("screening_sessions")
