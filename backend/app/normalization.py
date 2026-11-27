import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


def normalize_phone_number(value: str) -> str:
    """Return a valid phone number in E.164, assuming India for national input."""
    try:
        parsed = phonenumbers.parse(value, "IN")
    except NumberParseException as exc:
        raise ValueError("Enter a valid phone number. Use +country code for numbers outside India.") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Enter a valid phone number. Use +country code for numbers outside India.")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalize_job_title(value: str) -> str:
    """Collapse whitespace and case-fold a title for role matching."""
    return re.sub(r"\s+", " ", value.strip()).casefold()
