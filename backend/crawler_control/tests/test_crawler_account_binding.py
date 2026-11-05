"""Crawler account binding for a run (2026-11-05).

Two gaps this covers:

1. a job had no way to name an account — every job silently used the
   ``default`` group, so an operator could not tell which identity would
   crawl;
2. even when a run carried an account, only the DrissionPage fallback sent
   its cookies — plain HTTP requests were anonymous and hit the login wall
   first.

The API/service tests pin the first behaviour, the middleware tests the
second.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_control.models import CrawlRunEvent  # noqa: E402
from crawler_control.services import (  # noqa: E402
    mark_session_expired,
    start_run,
)
from crawler_control.tests.test_crawl_jobs_api import CrawlJobCreateApiTests  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)


class AccountResolutionTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.account = self.make_account(label="主账号")
        self.other = self.make_account(label="备用账号")

    def test_pinned_account_is_used_and_logged(self):
        job = self.make_job(name="Pinned", account=self.account)
        run = start_run(job)
        self.assertEqual(run.account, self.account)
        event = CrawlRunEvent.objects.get(run=run, code="RUN_ACCOUNT_SELECTED")
        self.assertEqual(event.level, "INFO")
        self.assertIn("主账号", event.message)

    def test_auto_selection_picks_a_group_account_and_logs_it(self):
        job = self.make_job(name="Auto")
        run = start_run(job)
        self.assertIsNotNone(run.account)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="RUN_ACCOUNT_SELECTED").exists())

    def test_unusable_pinned_account_falls_back_and_says_why(self):
        mark_session_expired(self.account)
        job = self.make_job(name="Expired pin", account=self.account)
        run = start_run(job)
        self.assertEqual(run.account, self.other)
        event = CrawlRunEvent.objects.get(run=run, code="ACCOUNT_FALLBACK")
        self.assertEqual(event.level, "WARNING")
        self.assertIn("主账号", event.message)
        self.assertIn("EXPIRED", event.message)

    def test_no_usable_account_anywhere_starts_anonymously(self):
        mark_session_expired(self.account)
        mark_session_expired(self.other)
        job = self.make_job(name="Nobody", account=self.account)
        run = start_run(job)
        self.assertIsNone(run.account)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="RUN_UNAUTHENTICATED").exists())
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="ACCOUNT_FALLBACK").exists())

    def test_valid_session_without_cookies_is_not_selectable(self):
        """The 2026-11-05 login-wall root cause: a placeholder session marked
        VALID carried zero cookies, so the run looked authenticated but was
        anonymous."""

        from crawler_control.services import record_account_session

        fake = self.make_account(label="占位账号")
        record_account_session(fake, {"joybuy_session": "public-homepage-demo"})
        fake.refresh_from_db()
        self.assertEqual(fake.session_status, "VALID")

        job = self.make_job(name="Placeholder pin", account=fake)
        run = start_run(job)
        self.assertNotEqual(run.account, fake)
        event = CrawlRunEvent.objects.get(run=run, code="ACCOUNT_FALLBACK")
        self.assertIn("没有可用 Cookie", event.message)


class AccountCookieTests(unittest.TestCase):
    def test_third_party_cookies_are_never_replayed_to_the_source(self):
        from joybuy_crawler.account_session import joybuy_cookie_pairs

        pairs = joybuy_cookie_pairs(
            [
                {"name": "pinId", "value": "abc", "domain": ".joybuy.co.uk"},
                {"name": "csm", "value": "def", "domain": "www.joybuy.co.uk"},
                {"name": "c_user", "value": "facebook-id", "domain": ".facebook.com"},
                {"name": "", "value": "nameless", "domain": ".joybuy.co.uk"},
            ]
        )
        self.assertEqual(pairs, {"pinId": "abc", "csm": "def"})

    def _spider(self, pool):
        class Spider:
            run = object()
            logger = mock.Mock()
            account_pool = pool

        return Spider()

    def test_middleware_attaches_the_active_account_cookies(self):
        from joybuy_crawler.account_rotation import AccountPool
        from joybuy_crawler.middlewares import AccountCookieMiddleware
        from scrapy.http import Request

        pool = AccountPool([{"public_id": "a", "label": "A", "cookies": {"pinId": "abc"}}])
        middleware = AccountCookieMiddleware()
        middleware._pool = pool  # pool already built
        request = Request("https://www.joybuy.co.uk/s?k=kettle")
        middleware.process_request(request, self._spider(pool))
        # CookiesMiddleware is disabled for crawl runs, so this middleware has
        # to write the header itself — Request.cookies alone reaches nobody.
        self.assertEqual(request.headers.get("Cookie"), b"pinId=abc")

    def test_request_specific_cookie_wins_over_the_account_default(self):
        from joybuy_crawler.account_rotation import AccountPool
        from joybuy_crawler.middlewares import AccountCookieMiddleware
        from scrapy.http import Request

        pool = AccountPool([{"public_id": "a", "label": "A", "cookies": {"pinId": "abc"}}])
        middleware = AccountCookieMiddleware()
        middleware._pool = pool
        request = Request("https://www.joybuy.co.uk/s?k=kettle", cookies={"pinId": "override"})
        middleware.process_request(request, self._spider(pool))
        self.assertEqual(request.headers.get("Cookie"), b"pinId=override")

    def test_no_account_means_no_cookie_header(self):
        from joybuy_crawler.account_rotation import AccountPool
        from joybuy_crawler.account_session import load_account_cookies
        from joybuy_crawler.middlewares import AccountCookieMiddleware
        from scrapy.http import Request

        class Spider:
            run = None
            logger = mock.Mock()

        self.assertEqual(load_account_cookies(Spider()), [])
        pool = AccountPool([])
        request = Request("https://www.joybuy.co.uk/s?k=kettle")
        middleware = AccountCookieMiddleware()
        middleware._pool = pool
        middleware.process_request(request, self._spider(pool))
        self.assertIsNone(request.headers.get("Cookie"))


class AccountRotationTests(unittest.TestCase):
    """Rotation cadence, isolation and ejection (no Scrapy, no database)."""

    def pool(self, *, budgets=None, clock=None):
        from joybuy_crawler.account_rotation import AccountPool

        budgets = budgets or {}
        return AccountPool(
            [
                {"public_id": "a", "label": "账号A", "group": "g", "cookies": {"pinId": "A"}},
                {"public_id": "b", "label": "账号B", "group": "g", "cookies": {"pinId": "B"}},
                {"public_id": "c", "label": "账号C", "group": "g", "cookies": {"pinId": "C"}},
            ],
            min_requests=budgets.get("min_requests", 2),
            max_requests=budgets.get("max_requests", 2),
            min_seconds=budgets.get("min_seconds", 60),
            max_seconds=budgets.get("max_seconds", 60),
            clock=clock or (lambda: 0.0),
        )

    def test_rotation_after_the_request_budget(self):
        pool = self.pool()
        self.assertFalse(pool.should_rotate())
        pool.record_request()
        self.assertFalse(pool.should_rotate())
        pool.record_request()
        self.assertTrue(pool.should_rotate())
        nxt = pool.rotate()
        self.assertEqual(nxt.label, "账号B")
        self.assertEqual(pool.rotations, 1)
        # A new stint starts with a fresh counter.
        self.assertFalse(pool.should_rotate())

    def test_rotation_after_the_time_budget(self):
        now = [0.0]
        pool = self.pool(budgets={"min_requests": 999, "max_requests": 999}, clock=lambda: now[0])
        self.assertFalse(pool.should_rotate())
        now[0] = 61.0
        self.assertTrue(pool.should_rotate())
        self.assertEqual(pool.rotate().label, "账号B")

    def test_each_stint_draws_a_new_budget_so_the_cadence_varies(self):
        pool = self.pool(budgets={"min_requests": 1, "max_requests": 6})
        budgets = set()
        for _ in range(12):
            budgets.add(pool._request_budget)  # noqa: SLF001 - asserting the draw itself
            pool.rotate()
        self.assertGreater(len(budgets), 1)

    def test_cookies_never_leak_between_accounts(self):
        pool = self.pool()
        first = pool.active
        self.assertEqual(first.cookies, {"pinId": "A"})
        pool.rotate()
        self.assertEqual(pool.active.cookies, {"pinId": "B"})
        # The previous account's jar is not merged into the new identity.
        self.assertNotIn("A", pool.active.cookies.values())

    def test_blocked_account_is_skipped_for_the_rest_of_the_run(self):
        pool = self.pool()
        pool.mark_blocked(reason="风控页")
        nxt = pool.rotate()
        self.assertEqual(nxt.label, "账号B")
        # Wrapping around must never come back to the blocked account.
        pool.rotate()
        self.assertEqual(pool.active.label, "账号C")
        pool.rotate()
        self.assertEqual(pool.active.label, "账号B")

    def test_all_blocked_returns_none_and_reports_exhaustion(self):
        pool = self.pool()
        for _ in range(3):
            pool.mark_blocked(reason="风控页")
            pool.rotate()
        self.assertTrue(pool.all_blocked)
        self.assertIsNone(pool.rotate())

    def test_single_account_never_rotates(self):
        from joybuy_crawler.account_rotation import AccountPool

        pool = AccountPool([{"public_id": "a", "label": "账号A", "cookies": {"pinId": "A"}}])
        self.assertFalse(pool.enabled)
        pool.record_request()
        self.assertFalse(pool.should_rotate())


class CrawlJobAccountApiTests(CrawlJobCreateApiTests):
    """The create endpoint accepts a pinned account and rejects bad ones."""

    def setUp(self):
        super().setUp()
        from crawler_control.services import create_crawler_account, record_account_session

        self.account = create_crawler_account(label="API 账号", account_group="default")
        record_account_session(
            self.account,
            {"cookies": [{"name": "pinId", "value": "x", "domain": ".joybuy.co.uk"}]},
        )

    def payload(self, **overrides):
        body = {
            "name": "账号绑定任务",
            "product_limit": 5,
            "source_ids": ["l2-electronics"],
            "reason": "测试",
        }
        body.update(overrides)
        return body

    def test_create_job_with_account_public_id_binds_it(self):
        from crawler_control.models import CrawlJob

        response = self.post_json(
            "/api/v1/admin/crawlers/jobs",
            self.payload(account_public_id=str(self.account.public_id)),
        )
        self.assertEqual(response.status_code, 201, response.content)
        job = CrawlJob.objects.get(public_id=response.json()["public_id"])
        self.assertEqual(job.account_id, self.account.pk)
        self.assertEqual(job.account_group, self.account.account_group)

    def test_unknown_account_is_rejected(self):
        response = self.post_json(
            "/api/v1/admin/crawlers/jobs",
            self.payload(account_public_id="00000000-0000-0000-0000-000000000000"),
        )
        self.assertEqual(response.status_code, 404)

    def test_disabled_account_cannot_be_pinned(self):
        from crawler_control.models import CrawlerAccount

        self.account.status = CrawlerAccount.Status.DISABLED
        self.account.save(update_fields=["status", "updated_at"])
        response = self.post_json(
            "/api/v1/admin/crawlers/jobs",
            self.payload(account_public_id=str(self.account.public_id)),
        )
        self.assertEqual(response.status_code, 400)
        body = json.dumps(response.json(), ensure_ascii=False)
        self.assertIn("ACCOUNT_UNAVAILABLE", body)
        self.assertIn("不能指定给任务", body)

    def test_without_account_the_job_stays_group_based(self):
        from crawler_control.models import CrawlJob

        response = self.post_json("/api/v1/admin/crawlers/jobs", self.payload())
        self.assertEqual(response.status_code, 201, response.content)
        job = CrawlJob.objects.get(public_id=response.json()["public_id"])
        self.assertIsNone(job.account_id)
        self.assertEqual(job.account_group, "default")


class AccountDeletionTests(CrawlerControlTestBase):
    """Deleting an account must not erase the identity behind past runs."""

    def setUp(self):
        super().setUp()
        self.account = self.make_account(label="待删账号")

    def test_refuses_while_a_run_is_still_using_it(self):
        from crawler_control.domain import CrawlAccountStateInvalid
        from crawler_control.services import delete_crawler_account

        start_run(self.make_job(name="Running job", account=self.account))
        with self.assertRaises(CrawlAccountStateInvalid):
            delete_crawler_account(self.account)

    def test_soft_delete_clears_the_session_but_keeps_run_attribution(self):
        from crawler_control.models import CrawlRun
        from crawler_control.services import complete_run, delete_crawler_account

        run = start_run(self.make_job(name="Finished job", account=self.account))
        complete_run(run, outcome=CrawlRun.Status.SUCCEEDED)

        delete_crawler_account(self.account, reason="退役")
        self.account.refresh_from_db()
        run.refresh_from_db()
        self.assertIsNotNone(self.account.deleted_at)
        self.assertEqual(self.account.session_cipher, "")
        self.assertEqual(self.account.status, "DISABLED")
        # History keeps pointing at the row, so the run log still names it.
        self.assertEqual(run.account_id, self.account.pk)
