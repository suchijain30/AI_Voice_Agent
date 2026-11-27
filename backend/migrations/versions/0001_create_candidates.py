"""Create candidate foundation table.

Revision ID: 0001_create_candidates
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_create_candidates"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("job_title", sa.String(length=200), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("years_of_experience", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidates_phone_number", "candidates", ["phone_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_candidates_phone_number", table_name="candidates")
    op.drop_table("candidates")
