"""Retry/backoff policy shared by every download path.

Framework-free on purpose: the same policy backs the plain-HTTP fetch
facade, future Playwright workers and the Scrapy retry configuration, so
behaviour stays identical across paths and is testable without Twisted.
"""

import random

RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def is_retryable_status(status_code: int) -> bool:
    """429 and 5xx (plus 408) follow the retry policy; 403/401 never do."""

    return status_code in RETRYABLE_STATUS_CODES


def compute_backoff_delay(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    factor: float = 2.0,
    cap_seconds: float = 60.0,
    jitter_ratio: float = 0.25,
    retry_after_seconds: float | None = None,
    rng: random.Random | None = None,
) -> float:
    """Exponential backoff with jitter, honouring server Retry-After.

    ``attempt`` starts at 1. The delay grows ``base * factor**(attempt-1)``
    up to ``cap_seconds``, gets up to ``jitter_ratio`` of multiplicative
    jitter, and never undercuts a server-provided Retry-After.
    """

    if attempt < 1:
        raise ValueError("attempt must start at 1.")
    if base_seconds <= 0 or factor <= 0 or cap_seconds <= 0:
        raise ValueError("base_seconds, factor and cap_seconds must be positive.")
    if jitter_ratio < 0:
        raise ValueError("jitter_ratio cannot be negative.")
    rng = rng or random.Random()
    delay = min(cap_seconds, base_seconds * (factor ** (attempt - 1)))
    delay += delay * jitter_ratio * rng.random()
    if retry_after_seconds is not None:
        if retry_after_seconds < 0:
            raise ValueError("retry_after_seconds cannot be negative.")
        delay = max(delay, retry_after_seconds)
    return delay
