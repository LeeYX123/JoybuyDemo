import logging
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.test import override_settings  # noqa: E402

from crawler_control.services import complete_run, start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402

SCRAPY_AVAILABLE = find_spec("scrapy") is not None
PLAYWRIGHT_AVAILABLE = find_spec("playwright") is not None


class BackoffAndRedactionTests(unittest.TestCase):
    def test_backoff_growth_cap_jitter_and_retry_after(self):
        from joybuy_crawler.core.policies import compute_backoff_delay

        deterministic = __import__("random").Random(42)
        delays = [
            compute_backoff_delay(
                attempt,
                base_seconds=1,
                factor=2,
                cap_seconds=30,
                jitter_ratio=0,
                rng=deterministic,
            )
            for attempt in range(1, 9)
        ]
        self.assertEqual(
            [round(value, 3) for value in delays],
            [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0],
            "Delays must grow exponentially and respect the cap.",
        )

        jittered = compute_backoff_delay(
            2, base_seconds=1, factor=2, cap_seconds=30, jitter_ratio=0.5, rng=deterministic
        )
        self.assertTrue(2.0 <= jittered <= 3.0)

        self.assertEqual(
            compute_backoff_delay(1, retry_after_seconds=7, rng=deterministic),
            7.0,
            "Server Retry-After must never be undercut.",
        )
        self.assertEqual(
            compute_backoff_delay(
                1, base_seconds=8, jitter_ratio=0, retry_after_seconds=2, rng=deterministic
            ),
            8.0,
            "The computed delay must never undercut a server Retry-After.",
        )
        self.assertEqual(
            compute_backoff_delay(
                4, base_seconds=8, cap_seconds=60, jitter_ratio=0, rng=deterministic
            ),
            60.0,
        )
        with self.assertRaises(ValueError):
            compute_backoff_delay(0)

    def test_retryable_status_classification(self):
        from joybuy_crawler.core.policies import is_retryable_status

        for status in (408, 429, 500, 502, 503, 504):
            self.assertTrue(is_retryable_status(status), status)
        for status in (200, 301, 403, 404, 410, 418):
            self.assertFalse(is_retryable_status(status), status)

    def test_headers_text_and_log_records_are_redacted(self):
        from joybuy_crawler.core.redaction import (
            SensitiveDataFilter,
            redact_headers,
            redact_text,
        )

        redacted = redact_headers(
            {"Cookie": "session=TOPSECRET", "Accept": "text/html", "authorization": "Bearer xyz"}
        )
        self.assertEqual(redacted["Cookie"], "[REDACTED]")
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["Accept"], "text/html")

        scrubbed = redact_text("login ok cookie: abc123; authorization: Bearer ttt")
        self.assertNotIn("abc123", scrubbed)
        self.assertNotIn("ttt", scrubbed)
        self.assertIn("[REDACTED]", scrubbed)

        logger = logging.getLogger("joybuy_crawler.filter-test")
        logger.addFilter(SensitiveDataFilter())
        records = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())
        logger.addHandler(handler)
        logger.propagate = False
        logger.warning("cookie: leakvalue")
        self.assertIn("[REDACTED]", records[0])
        self.assertNotIn("leakvalue", records[0])


class FetchPathTests(CrawlerControlTestBase):
    """HTTP and browser download paths verified against a local fixture site."""

    def setUp(self):
        super().setUp()
        # Keep raw-response archives out of the shared var/raw dev tree.
        self._raw_tmp = tempfile.TemporaryDirectory(prefix="joybuy-raw-runtime-")
        self.addCleanup(self._raw_tmp.cleanup)
        raw_override = override_settings(CRAWL_RAW_ROOT=Path(self._raw_tmp.name))
        raw_override.enable()
        self.addCleanup(raw_override.disable)
        self.make_account()
        from joybuy_crawler.fixtures.http_site import CrawlerFixtureServer

        self.site = CrawlerFixtureServer()
        self.addCleanup(self.site.stop)

    def test_http_fetch_retries_429_honouring_retry_after(self):
        from joybuy_crawler.core.http_client import fetch_url

        sleeps = []
        result = fetch_url(
            f"{self.site.base_url}/flaky?fails=2",
            max_attempts=4,
            base_seconds=0.5,
            sleep=sleeps.append,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"flaky-ok", result.body)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(sleeps), 2)
        for delay in sleeps:
            self.assertGreaterEqual(delay, 1.0, "Retry-After: 1 must be honoured.")

    def test_http_fetch_gives_up_after_persistent_500(self):
        from joybuy_crawler.core.http_client import FetchFailed, fetch_url

        with self.assertRaises(FetchFailed):
            fetch_url(
                f"{self.site.base_url}/boom?fails=10",
                max_attempts=3,
                base_seconds=0.1,
                sleep=lambda _: None,
            )

    def test_http_fetch_returns_non_retryable_status_without_retry(self):
        from joybuy_crawler.core.http_client import fetch_url

        sleeps = []
        result = fetch_url(
            f"{self.site.base_url}/missing",
            max_attempts=4,
            sleep=sleeps.append,
        )
        self.assertEqual(result.status_code, 404)
        self.assertEqual(sleeps, [])

    def test_sensitive_cookies_never_reach_logs(self):
        from joybuy_crawler.core.http_client import fetch_url

        records = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())
        crawler_logger = logging.getLogger("joybuy_crawler.http")
        crawler_logger.addHandler(handler)
        crawler_logger.setLevel(logging.DEBUG)
        try:
            result = fetch_url(
                f"{self.site.base_url}/echo",
                headers={"Cookie": "session=TOPSECRETVALUE"},
            )
        finally:
            crawler_logger.removeHandler(handler)

        self.assertEqual(result.status_code, 200)
        emitted = "\n".join(records)
        self.assertIn("[REDACTED]", emitted)
        self.assertNotIn("TOPSECRETVALUE", emitted)

    @unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright is not installed")
    def test_browser_path_renders_javascript(self):
        from joybuy_crawler.core.browser import BrowserWorker

        try:
            with BrowserWorker() as worker:
                html = worker.fetch(f"{self.site.base_url}/js", wait_for_selector="#content")
        except Exception as exc:  # browsers not installed in this environment
            raise unittest.SkipTest(f"Chromium unavailable: {exc}") from exc
        self.assertIn("rendered-by-chromium", html)

    @unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
    def test_scrapy_pipeline_archives_raw_response(self):
        from joybuy_crawler.pipelines import RawArchivePipeline
        from scrapy.http import TextResponse

        run = start_run(self.make_job(name="Pipeline job"))
        pipeline = RawArchivePipeline()
        pipeline.open_spider(type("SpiderStub", (), {"crawl_run_public_id": str(run.public_id)})())
        response = TextResponse(
            f"{self.site.base_url}/ok",
            status=200,
            body=b"<html><body>static-ok</body></html>",
            headers={b"Content-Type": [b"text/html"]},
        )
        pipeline.process_response(response, None)
        complete_run(run, outcome="SUCCEEDED")

        row = run.raw_responses.get()
        self.assertEqual(row.status_code, 200)
        self.assertEqual(row.byte_size, len(response.body))
        self.assertFalse(row.file_deleted)
        self.assertEqual(
            row.response_hash,
            __import__("hashlib").sha256(response.body).hexdigest(),
        )
        self.assertIn(str(run.public_id), row.relative_path)

    @unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
    def test_scrapy_settings_wire_backoff_redaction_and_archive(self):
        from joybuy_crawler import settings as scrapy_settings

        self.assertIn(429, scrapy_settings.RETRY_HTTP_CODES)
        for status in (500, 502, 503, 504):
            self.assertIn(status, scrapy_settings.RETRY_HTTP_CODES)
        self.assertTrue(scrapy_settings.ROBOTSTXT_OBEY)
        self.assertIn(
            "joybuy_crawler.middlewares.HeaderRedactionMiddleware",
            scrapy_settings.DOWNLOADER_MIDDLEWARES,
        )
        self.assertIn(
            "joybuy_crawler.pipelines.RawArchivePipeline",
            scrapy_settings.ITEM_PIPELINES,
        )
        self.assertTrue(Path(scrapy_settings.HTTPCACHE_DIR).is_absolute())

    @unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
    def test_raw_archive_pipeline_requires_bound_run(self):
        from joybuy_crawler.pipelines import RawArchivePipeline

        pipeline = RawArchivePipeline()
        with self.assertRaises(RuntimeError):
            pipeline.open_spider(type("SpiderStub", (), {"crawl_run_public_id": None})())
