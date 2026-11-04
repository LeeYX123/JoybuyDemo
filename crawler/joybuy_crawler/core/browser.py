"""Playwright browser worker for pages that need JavaScript or sessions.

The import is lazy: environments without Playwright can still import this
module and run the HTTP path; the browser path fails with an actionable
error telling the operator to install browsers first.
"""

import logging

from joybuy_crawler.core.redaction import SensitiveDataFilter

logger = logging.getLogger("joybuy_crawler.browser")
logger.addFilter(SensitiveDataFilter())

DEFAULT_NAVIGATION_TIMEOUT_MS = 30_000


class BrowserUnavailable(RuntimeError):
    pass


def _sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable(
            "The playwright package is not installed; run "
            "`pip install -r crawler/requirements.txt` first."
        ) from exc
    return sync_playwright


class BrowserWorker:
    """Context-managed headless Chromium worker (low concurrency by design)."""

    def __init__(
        self, *, headless: bool = True, navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS
    ):
        self.headless = headless
        self.navigation_timeout_ms = navigation_timeout_ms
        self._playwright = None
        self._browser = None

    def __enter__(self) -> "BrowserWorker":
        sync_playwright = _sync_playwright()
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        except Exception as exc:
            self.__exit__(None, None, None)
            raise BrowserUnavailable(
                "Chromium could not be launched; run `python -m playwright install chromium`."
            ) from exc
        return self

    def __exit__(self, *exc_info) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def fetch(self, url: str, *, wait_for_selector: str | None = None) -> str:
        """Render one URL in a fresh context and return the resulting HTML."""

        if self._browser is None:
            raise BrowserUnavailable("BrowserWorker is not started; use it as a context manager.")
        context = self._browser.new_context()
        try:
            page = context.new_page()
            page.set_default_navigation_timeout(self.navigation_timeout_ms)
            response = page.goto(url, wait_until="domcontentloaded")
            if response is not None and response.status >= 400:
                logger.warning("Browser fetch of %s returned status %s", url, response.status)
            if wait_for_selector:
                page.wait_for_selector(wait_for_selector)
            html = page.content()
            logger.info("Browser fetch of %s completed (%d chars)", url, len(html))
            return html
        finally:
            context.close()
