import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    validate_email(normalized)
    return normalized


def normalize_phone(value: str) -> str:
    normalized = re.sub(r"[\s()-]", "", value.strip())
    if not PHONE_PATTERN.fullmatch(normalized):
        raise ValidationError("Enter a valid E.164 phone number.")
    return normalized


def normalize_target(channel: str, target: str) -> str:
    if channel == "EMAIL":
        return normalize_email(target)
    if channel == "PHONE":
        return normalize_phone(target)
    raise ValidationError("Unsupported verification channel.")


def normalize_identifier(value: str) -> tuple[str, str]:
    if "@" in value:
        return "email", normalize_email(value)
    return "phone_e164", normalize_phone(value)
