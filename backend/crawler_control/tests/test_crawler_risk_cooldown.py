"""Risk-control cool-down persistence (2026-11-16).

Before this change ``ACCOUNT_RISK_ROTATED`` only removed an account from the
in-process ``AccountPool``: the DB row stayed ACTIVE/VALID with
``risk_flagged_at=NULL``, so the next run picked the same burned identity and
the group was exhausted again within minutes (03 group: 10/10 accounts, then
32 minutes of empty ``/error403`` crawling).

These tests cover the four required behaviours: the flag is written, a cooled
account is not selected, an expired cool-down is selectable again, and a group
whose every selectable account is cooling down refuses to start with a Chinese
reason instead of spinning anonymously.
"""

import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.test import TestCase  # noqa: E402
from django.utils import timezone  # noqa: E402

from crawler_control.domain import CrawlAccountStateInvalid  # noqa: E402
from crawler_control.models import CrawlerAccount, CrawlJob, CrawlRun  # noqa: E402
from crawler_control.services import (  # noqa: E402
    mark_account_risk_cooldown,
    risk_cooldown_hours,
    start_run,
    usable_accounts_for_run,
)
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)


class RiskCooldownFlagTests(CrawlerControlTestBase):
    def test_risk_hit_is_persisted_without_pausing_the_account(self):
        account = self.make_account(label="Rotated away")
        self.assertIsNone(account.risk_flagged_at)

        flagged = mark_account_risk_cooldown(
            account.public_id, reason="详情页风控验证码，本 run 内被移出账号池"
        )

        self.assertIsNotNone(flagged)
        flagged.refresh_from_db()
        self.assertIsNotNone(flagged.risk_flagged_at)
        self.assertEqual(flagged.risk_reason, "详情页风控验证码，本 run 内被移出账号池")
        # The crawl that rotated it away is still running with other accounts:
        # this write must not pause the account like flag_account_risk_control.
        self.assertEqual(flagged.status, CrawlerAccount.Status.ACTIVE)

    def test_middleware_bridge_writes_the_flag_with_page_context(self):
        from joybuy_crawler.middlewares import RiskControlRenderMiddleware

        detail = self.make_account(label="Detail hit", group="数据抓取03")
        listing = self.make_account(label="Listing hit", group="数据抓取03")

        RiskControlRenderMiddleware._persist_risk_cooldown(
            SimpleNamespace(public_id=str(detail.public_id)),
            url="https://www.joybuy.co.uk/dp/100020670022401",
        )
        RiskControlRenderMiddleware._persist_risk_cooldown(
            SimpleNamespace(public_id=str(listing.public_id)),
            url="https://www.joybuy.co.uk/s?k=coat",
        )
        # Real 2026-11-16 wall: the risk page carries the blocked page in an
        # encoded returnUrl, so the label must look past the encoding.
        encoded = self.make_account(label="Encoded detail hit", group="数据抓取03")
        RiskControlRenderMiddleware._persist_risk_cooldown(
            SimpleNamespace(public_id=str(encoded.public_id)),
            url=(
                "https://www.joybuy.co.uk/user/risk/pic?returnUrl=https%3A%2F%2F"
                "www.joybuy.co.uk%2Fdp%2Fx%2F100017690252319%3Ffoo%3D1"
            ),
        )

        detail.refresh_from_db()
        listing.refresh_from_db()
        encoded.refresh_from_db()
        self.assertIsNotNone(detail.risk_flagged_at)
        self.assertTrue(detail.risk_reason.startswith("详情页风控验证码"))
        self.assertIsNotNone(listing.risk_flagged_at)
        self.assertTrue(listing.risk_reason.startswith("列表页风控验证码"))
        self.assertTrue(encoded.risk_reason.startswith("详情页风控验证码"))

    def test_unknown_public_id_is_ignored(self):
        # A stale label rotated away in the crawler must not raise.
        self.assertIsNone(
            mark_account_risk_cooldown("00000000-0000-0000-0000-000000000000", reason="风控页")
        )


class RiskCooldownSelectionTests(CrawlerControlTestBase):
    GROUP = "数据抓取03"

    def test_cooled_account_is_not_selected_and_is_reported(self):
        fresh = self.make_account(label="Fresh", group=self.GROUP)
        cooled = self.make_account(label="Cooling", group=self.GROUP)
        mark_account_risk_cooldown(cooled.public_id, reason="风控页")

        job = self.make_job(name="Partially cooled", account_group=self.GROUP)
        selected = usable_accounts_for_run(job)
        self.assertEqual([account.pk for account in selected], [fresh.pk])

        run = start_run(job)
        self.assertEqual(run.account, fresh)
        event = run.events.get(code="ACCOUNTS_RISK_COOLDOWN_SKIPPED")
        self.assertEqual(event.level, "INFO")
        self.assertIn("1 个", event.message)
        self.assertIn(cooled.label, event.message)

    def test_account_is_selectable_again_after_the_cooldown(self):
        account = self.make_account(label="Old hit", group=self.GROUP)
        stale = timezone.now() - timedelta(hours=risk_cooldown_hours() + 1)
        mark_account_risk_cooldown(account.public_id, reason="风控页", observed_at=stale)

        job = self.make_job(name="After cooldown", account_group=self.GROUP)
        self.assertEqual([item.pk for item in usable_accounts_for_run(job)], [account.pk])
        run = start_run(job)
        self.assertEqual(run.account, account)
        self.assertFalse(run.events.filter(code="ACCOUNTS_RISK_COOLDOWN_SKIPPED").exists())

    @patch.dict("os.environ", {"CRAWLER_RISK_COOLDOWN_HOURS": "1"})
    def test_cooldown_window_follows_the_environment(self):
        account = self.make_account(label="One hour window", group=self.GROUP)
        two_hours_ago = timezone.now() - timedelta(hours=2)
        mark_account_risk_cooldown(account.public_id, reason="风控页", observed_at=two_hours_ago)

        job = self.make_job(name="Short window", account_group=self.GROUP)
        self.assertEqual([item.pk for item in usable_accounts_for_run(job)], [account.pk])

    def test_group_fully_in_cooldown_refuses_start_with_chinese_reason(self):
        first = self.make_account(label="Cooling A", group=self.GROUP)
        second = self.make_account(label="Cooling B", group=self.GROUP)
        for account in (first, second):
            mark_account_risk_cooldown(account.public_id, reason="详情页风控验证码")

        job = self.make_job(name="All cooled", account_group=self.GROUP)
        with self.assertRaises(CrawlAccountStateInvalid) as caught:
            start_run(job)

        message = str(caught.exception)
        self.assertIn(self.GROUP, message)
        self.assertIn("组账号全部处于风控冷却期", message)
        self.assertIn("补充账号", message)
        # Fast failure, not a silent anonymous run: the job stays READY and
        # no run row is created.
        job.refresh_from_db()
        self.assertEqual(job.status, CrawlJob.Status.READY)
        self.assertFalse(CrawlRun.objects.filter(job=job).exists())


class RiskCooldownEnvironmentTests(TestCase):
    @patch.dict("os.environ", {"CRAWLER_RISK_COOLDOWN_HOURS": "2.5"})
    def test_env_override_is_honoured(self):
        self.assertEqual(risk_cooldown_hours(), 2.5)

    @patch.dict("os.environ", {"CRAWLER_RISK_COOLDOWN_HOURS": "not-a-number"})
    def test_invalid_env_falls_back_to_six_hours(self):
        self.assertEqual(risk_cooldown_hours(), 6.0)
