from django.core.validators import validate_email


def normalize_staff_email(value: str) -> str:
    normalized = value.strip().casefold()
    validate_email(normalized)
    return normalized
