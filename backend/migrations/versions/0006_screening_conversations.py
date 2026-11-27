"""Add deterministic screening conversation state and text turn history."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_screening_conversations"
down_revision: Union[str, None] = "0005_screening_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screening_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("screening_session_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="ready", nullable=False),
        sa.Column("current_question_key", sa.String(length=64), nullable=True),
        sa.Column("clarification_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_clarification_attempts", sa.Integer(), server_default="2", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('ready', 'awaiting_response', 'clarification_needed', 'interrupted', "
            "'completed', 'declined', 'incomplete')",
            name="ck_screening_conversations_state",
        ),
        sa.CheckConstraint("clarification_attempts >= 0", name="ck_screening_conversations_attempts"),
        sa.CheckConstraint(
            "max_clarification_attempts >= 1 AND max_clarification_attempts <= 5",
            name="ck_screening_conversations_max_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["screening_session_id"], ["screening_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_screening_conversations_screening_session_id",
        "screening_conversations",
        ["screening_session_id"],
        unique=True,
    )

    op.create_table(
        "screening_conversation_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=True),
        sa.Column("turn_type", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "speaker IN ('agent', 'candidate', 'system')", name="ck_screening_conversation_turn_speaker"
        ),
        sa.CheckConstraint(
            "turn_type IN ('question', 'response', 'clarification', 'repetition', 'system_event')",
            name="ck_screening_conversation_turn_type",
        ),
        sa.CheckConstraint("turn_number >= 1", name="ck_screening_conversation_turn_number"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["screening_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "turn_number", name="uq_screening_conversation_turn_number"),
    )
    op.create_index(
        "ix_screening_conversation_turns_conversation_id",
        "screening_conversation_turns",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_screening_conversation_turns_conversation_id", table_name="screening_conversation_turns")
    op.drop_table("screening_conversation_turns")
    op.drop_index("ix_screening_conversations_screening_session_id", table_name="screening_conversations")
    op.drop_table("screening_conversations")
