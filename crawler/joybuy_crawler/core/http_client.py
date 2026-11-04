"""Plain-HTTP download path with policy-driven retries.

Used where a page is reachable without JavaScript. 429/5xx/408 responses
are retried with :mod:`joybuy_crawler.core.policies` backoff (honouring
``Retry-After``); exhausting the retry budget raises :class:`FetchFailed`.
Non-retryable statuses (404, 403, ...) come back as a normal FetchResult
without any retry so the caller decides how to handle them.
"""

import logging
import time
import urllib.error
import urllib.request

from joybuy_crawler.core.policies import compute_backoff_delay, is_retryable_status
from joybuy_crawler.core.redaction import SensitiveDataFilter, redact_headers

logger = logging.getLogger("joybuy_crawler.http")
logger.addFilter(SensitiveDataFilter())

USER_AGENT = "JoybuyResearchBot/1.0 (+authorized-research)"


class FetchFailed(RuntimeError):
    """Raised when every attempt for a URL has been exhausted."""


class FetchResult:
    def __init__(self, *, url, status_code, body, headers, attempts):
        self.url = url
        self.status_code = status_code
        self.body = body
        self.headers = headers
        self.attempts = attempts

    def __repr__(self):
        return f"FetchResult(status={self.status_code}, attempts={self.attempts})"


def _read_retry_after(headers) -> float | None:
    raw = headers.get("Retry-After") if headers else None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def fetch_url(
    url: str,
    *,
    headers: dict | None = None,
    max_attempts: int = 4,
    base_seconds: float = 1.0,
    cap_seconds: float = 30.0,
    timeout_seconds: float = 30.0,
    sleep=time.sleep,
    opener: urllib.request.OpenerDirector | None = None,
) -> FetchResult:
    """Fetch one URL, retrying retryable failures with exponential backoff."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = opener or urllib.request.build_opener()
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                body = response.read()
                logger.info(
                    "GET %s -> %s (attempt %d, request_headers=%s, response_headers=%s)",
                    url,
                    response.status,
                    attempt,
                    redact_headers(request.headers),
                    redact_headers(response.headers),
                )
                return FetchResult(
                    url=url,
                    status_code=response.status,
                    body=body,
                    headers=dict(response.headers),
                    attempts=attempt,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read()
            logger.warning(
                "GET %s -> %s (attempt %d, request_headers=%s, response_headers=%s)",
                url,
                exc.code,
                attempt,
                redact_headers(request.headers),
                redact_headers(exc.headers),
            )
            retry_after = _read_retry_after(exc.headers)
            if not is_retryable_status(exc.code):
                return FetchResult(
                    url=url,
                    status_code=exc.code,
                    body=body,
                    headers=dict(exc.headers),
                    attempts=attempt,
                )
            if attempt == max_attempts:
                raise FetchFailed(
                    f"All {max_attempts} attempts for {url} failed with status {exc.code}."
                ) from exc
            last_exception = exc
            delay = compute_backoff_delay(
                attempt,
                base_seconds=base_seconds,
                cap_seconds=cap_seconds,
                retry_after_seconds=retry_after,
            )
            logger.info("Retrying %s in %.2fs after status %s", url, delay, exc.code)
            sleep(delay)
        except urllib.error.URLError as exc:
            logger.warning("GET %s failed (attempt %d): %s", url, attempt, exc.reason)
            last_exception = exc
            if attempt == max_attempts:
                break
            delay = compute_backoff_delay(
                attempt, base_seconds=base_seconds, cap_seconds=cap_seconds
            )
            logger.info("Retrying %s in %.2fs after network error", url, delay)
            sleep(delay)

    raise FetchFailed(f"All {max_attempts} attempts for {url} failed: {last_exception}")
