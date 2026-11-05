"""HTTP cache policy: never replay redirects or blocked pages.

The 2026-11-05 bug this prevents: an anonymous request bounced to ``/login``
(307) was cached under the listing URL. The cache key ignores cookies, so a
later run carrying a valid account session was served the cached redirect
and never touched the network — the run reported "login wall" while the
cookies were perfectly valid.
"""

import sys
import unittest
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

try:
    import scrapy  # noqa: F401

    SCRAPY_AVAILABLE = True
except ImportError:  # pragma: no cover - scrapy is a runtime dependency
    SCRAPY_AVAILABLE = False

LISTING_HTML = "<html><body>" + ("<div class='card'>Kettle</div>" * 300) + "</body></html>"


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class CachePolicyTests(unittest.TestCase):
    def policy(self):
        from joybuy_crawler.cache_policy import SuccessOnlyCachePolicy
        from scrapy.settings import Settings

        return SuccessOnlyCachePolicy(settings=Settings())

    def response(self, *, status, url, body=LISTING_HTML):
        from scrapy.http import HtmlResponse, Request

        return HtmlResponse(
            url=url,
            status=status,
            body=body.encode("utf-8"),
            encoding="utf-8",
            request=Request(url),
        )

    def test_redirects_are_never_cached(self):
        url = "https://www.joybuy.co.uk/s?k=Kettles"
        response = self.response(status=307, url=url)
        self.assertFalse(self.policy().should_cache_response(response, response.request))

    def test_successful_listing_is_cached(self):
        url = "https://www.joybuy.co.uk/s?k=Kettles"
        response = self.response(status=200, url=url)
        self.assertTrue(self.policy().should_cache_response(response, response.request))

    def test_login_page_is_never_cached(self):
        url = "https://www.joybuy.co.uk/login?returnUrl=%2Fs%3Fk%3DKettles"
        response = self.response(status=200, url=url, body="<html><body>Sign in</body></html>")
        self.assertFalse(self.policy().should_cache_response(response, response.request))

    def test_risk_control_page_is_never_cached(self):
        url = "https://www.joybuy.co.uk/s?k=Kettles"
        body = "<html><body><h1>Access Denied</h1>verify you are human</body></html>"
        response = self.response(status=200, url=url, body=body)
        self.assertFalse(self.policy().should_cache_response(response, response.request))
