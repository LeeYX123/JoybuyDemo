"""Crawler-side media download facade (WP-18).

Downloads a media URL through the shared HTTP client (policy retries,
redacted logs) and hands the raw bytes to the backend pipeline; the crawler
never parses or stores media itself.
"""

from joybuy_crawler.core.http_client import FetchFailed, fetch_url


class MediaDownloadFailed(RuntimeError):
    pass


def download_media(url: str, *, max_attempts: int = 4, **fetch_kwargs) -> bytes:
    """Download one media URL; raises :class:`MediaDownloadFailed` on failure."""

    try:
        result = fetch_url(url, max_attempts=max_attempts, **fetch_kwargs)
    except FetchFailed as exc:
        raise MediaDownloadFailed(str(exc)) from exc
    if result.status_code != 200:
        raise MediaDownloadFailed(f"Download of {url} returned status {result.status_code}.")
    return result.body
