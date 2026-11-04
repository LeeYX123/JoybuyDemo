"""Sensitive-value redaction for logs and structured payloads.

Credentials — cookies, authorization headers, tokens — must never reach
logs, exports or error reports. Every logging path in the crawler goes
through :class:`SensitiveDataFilter` or :func:`redact_headers`.
"""

import logging
import re

SENSITIVE_HEADERS = frozenset(
    {"cookie", "set-cookie", "authorization", "proxy-authorization", "x-api-key"}
)
REDACTED_PLACEHOLDER = "[REDACTED]"

# Free-form log scrubbing: once a credential-like key appears, everything up
# to the end of the line is treated as sensitive and replaced.
_TEXT_SECRET_PATTERN = re.compile(
    r"(?i)\b(cookie|set-cookie|authorization|proxy-authorization|x-api-key|token)\b(\s*[:=]\s*).*"
)


def redact_headers(headers) -> dict:
    """Return a log-safe copy of a header mapping or iterable of pairs."""

    normalized = {}
    if hasattr(headers, "items"):
        pairs = headers.items()
    else:
        pairs = headers
    for key, value in pairs:
        lowered = str(key).casefold()
        if lowered in SENSITIVE_HEADERS:
            normalized[str(key)] = REDACTED_PLACEHOLDER
        else:
            normalized[str(key)] = str(value)
    return normalized


def redact_text(text: str) -> str:
    """Scrub credential-like ``key: value`` patterns from a free-form string."""

    return _TEXT_SECRET_PATTERN.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{REDACTED_PLACEHOLDER}", text
    )


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs credential patterns from every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = None
        return True
