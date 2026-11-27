"""Add normalized application keys and prevent duplicate applications.

Revision ID: 0002_duplicate_apps
Revises: 0001_create_candidates
"""
from collections import defaultdict
import re

from alembic import op
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
import sqlalchemy as sa

revision = "0002_duplicate_apps"
down_revision = "0001_create_candidates"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_candidates_phone_job_title_normalized"


def normalize_phone_number(value: str) -> str:
    """Migration-local copy of the application normalization rule."""
    try:
        parsed = phonenumbers.parse(value, "IN")
    except NumberParseException as exc:
        raise ValueError("invalid phone number") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("invalid phone number")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalize_job_title(value: str) -> str:
    """Keep this aligned with app.normalization.normalize_job_title."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, phone_number, job_title FROM candidates ORDER BY id")
    ).mappings().all()

    normalized_rows: list[tuple[object, str, str]] = []
    duplicate_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        try:
            phone_key = normalize_phone_number(row["phone_number"])
        except ValueError as exc:
            raise RuntimeError(
                "Cannot add duplicate-application protection: candidate "
                f"{row['id']} has an invalid phone number. No candidate records were changed. "
                "Correct that record and rerun the migration."
            ) from exc
        title_key = normalize_job_title(row["job_title"])
        normalized_rows.append((row["id"], phone_key, title_key))
        duplicate_groups[(phone_key, title_key)].append(str(row["id"]))

    duplicates = [
        (title_key, candidate_ids)
        for (_, title_key), candidate_ids in duplicate_groups.items()
        if len(candidate_ids) > 1
    ]
    if duplicates:
        details = "; ".join(
            f"normalized job title {title_key!r}, candidate IDs: {', '.join(candidate_ids)}"
            for title_key, candidate_ids in duplicates
        )
        raise RuntimeError(
            "Cannot add duplicate-application protection: existing duplicate applications were found. "
            "No candidate records were changed. Review the listed records, resolve duplicates manually, "
            f"and rerun the migration. {details}"
        )

    op.add_column("candidates", sa.Column("normalized_phone_number", sa.String(length=16), nullable=True))
    op.add_column("candidates", sa.Column("normalized_job_title", sa.String(length=600), nullable=True))
    for candidate_id, phone_key, title_key in normalized_rows:
        connection.execute(
            sa.text(
                "UPDATE candidates "
                "SET normalized_phone_number = :phone_key, normalized_job_title = :title_key "
                "WHERE id = :candidate_id"
            ),
            {"candidate_id": candidate_id, "phone_key": phone_key, "title_key": title_key},
        )
    op.alter_column("candidates", "normalized_phone_number", nullable=False)
    op.alter_column("candidates", "normalized_job_title", nullable=False)
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "candidates",
        ["normalized_phone_number", "normalized_job_title"],
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "candidates", type_="unique")
    op.drop_column("candidates", "normalized_job_title")
    op.drop_column("candidates", "normalized_phone_number")
