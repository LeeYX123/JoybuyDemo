import gzip
import hashlib
import tempfile
from datetime import timedelta
from pathlib import Path

from catalog.models import SourceCatalog, SourceCategory, SourceCategoryTreeVersion
from catalog.services import save_source_category_version
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from offers.models import Currency, Market

from crawler_control.domain import (
    CrawlAccountStateInvalid,
    CrawlJobParamsInvalid,
    CrawlJobStateInvalid,
    CrawlRunStateInvalid,
    CrawlSessionSecretInvalid,
    RawResponseInvalid,
    RiskControlPaused,
)
from crawler_control.models import CrawlerAccount, CrawlJob, CrawlRun
from crawler_control.services import (
    cancel_run,
    complete_run,
    create_crawl_job,
    create_crawler_account,
    flag_account_risk_control,
    load_account_session,
    mark_job_ready,
    mark_session_expired,
    pause_run,
    purge_expired_raw_responses,
    reactivate_account,
    record_account_session,
    record_raw_response,
    redact_sensitive_keys,
    resolve_raw_path,
    resume_run,
    start_run,
    update_run_progress,
)


class CrawlerControlTestBase(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.catalog, self.version = self._seed_category_tree()
        self.l2 = SourceCategory.objects.get(catalog=self.catalog, source_id="l2-electronics")
        self.l3 = SourceCategory.objects.get(catalog=self.catalog, source_id="l3-phones")

    def _seed_category_tree(self):
        version = save_source_category_version(
            source_system="joybuy",
            version_key="2026-11-02",
            captured_at=timezone.now(),
            nodes=[
                {"source_id": "l1-root", "name": "Root", "parent_source_id": None},
                {
                    "source_id": "l2-electronics",
                    "name": "Electronics",
                    "parent_source_id": "l1-root",
                },
                {
                    "source_id": "l3-phones",
                    "name": "Phones",
                    "parent_source_id": "l2-electronics",
                },
            ],
        )
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])
        catalog = SourceCatalog.objects.get(source_system="joybuy")
        return catalog, version

    def make_account(self, group="default", label=None, **kwargs):
        account = create_crawler_account(
            label=label or f"Account {group}", account_group=group, **kwargs
        )
        record_account_session(account, {"joybuy_session": "session-token-value"})
        return account

    def make_job(self, **kwargs):
        defaults = {
            "name": "Electronics crawl",
            "market": self.market,
            "source_catalog": self.catalog,
            "source_category": self.l2,
            "product_limit": 100,
            "created_via_defaults": True,
        }
        defaults.update(kwargs)
        defaults.pop("created_via_defaults", None)
        job = create_crawl_job(**defaults)
        return mark_job_ready(job)


class CrawlJobParamsTests(CrawlerControlTestBase):
    def test_job_defaults_and_param_validation(self):
        job = create_crawl_job(
            name="Default job",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=50,
        )
        self.assertEqual(job.review_target, 50)
        self.assertEqual(job.sync_mode, CrawlJob.SyncMode.INCREMENTAL)
        self.assertEqual(job.category_mode, CrawlJob.CategoryMode.INCLUDE_SUBCATEGORIES)
        self.assertEqual(job.locale, "en-GB")
        self.assertEqual(job.status, CrawlJob.Status.DRAFT)

        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Bad reviews",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                review_target=301,
            )
        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Bad reviews zero",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                review_target=0,
            )
        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Bad limit",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=0,
            )
        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Bad sort",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                listing_sort="CHEAPEST",
            )

    def test_include_subcategories_defaults_follow_category_depth(self):
        shallow = create_crawl_job(
            name="Second level",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=10,
        )
        deep = create_crawl_job(
            name="Third level",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l3,
            product_limit=10,
        )
        explicit = create_crawl_job(
            name="Explicit current only",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=10,
            include_subcategories=False,
        )
        self.assertEqual(shallow.category_mode, CrawlJob.CategoryMode.INCLUDE_SUBCATEGORIES)
        self.assertEqual(deep.category_mode, CrawlJob.CategoryMode.CURRENT_ONLY)
        self.assertEqual(explicit.category_mode, CrawlJob.CategoryMode.CURRENT_ONLY)

    def test_random_sort_persists_reproducible_seed(self):
        seeded = create_crawl_job(
            name="Random sampling",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=10,
            listing_sort=CrawlJob.ListingSort.RANDOM,
        )
        self.assertIsNotNone(seeded.random_seed)
        self.assertEqual(
            create_crawl_job(
                name="Default sort",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
            ).random_seed,
            None,
        )


class CrawlStateMachineTests(CrawlerControlTestBase):
    def test_start_run_requires_ready_and_snapshots_params(self):
        draft = create_crawl_job(
            name="Draft job",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=10,
        )
        with self.assertRaises(CrawlJobStateInvalid):
            start_run(draft)

        self.make_account()
        job = self.make_job(sync_mode=CrawlJob.SyncMode.FULL_REFRESH, review_target=80)
        run = start_run(job)
        job.refresh_from_db()
        self.assertEqual(job.status, CrawlJob.Status.RUNNING)
        self.assertEqual(run.status, CrawlRun.Status.RUNNING)
        self.assertEqual(run.params_snapshot["review_target"], 80)
        self.assertEqual(run.params_snapshot["sync_mode"], "FULL_REFRESH")
        self.assertEqual(run.params_snapshot["source_category_id"], "l2-electronics")
        self.assertIsNotNone(run.started_at)

    def test_run_completion_and_failure_policy(self):
        self.make_account()
        pausing_job = self.make_job(name="Pausing job")
        run = start_run(pausing_job)
        update_run_progress(run, discovered=40, downloaded=35, succeeded=30, failed=5)
        run.refresh_from_db()
        self.assertEqual(run.succeeded_count, 30)
        complete_run(run, outcome=CrawlRun.Status.SUCCEEDED)
        run.refresh_from_db()
        pausing_job.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.SUCCEEDED)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(pausing_job.status, CrawlJob.Status.COMPLETED)

        continuing_job = self.make_job(
            name="Continuing job",
            failure_strategy=CrawlJob.FailureStrategy.CONTINUE,
        )
        run2 = start_run(continuing_job)
        complete_run(run2, outcome=CrawlRun.Status.FAILED)
        continuing_job.refresh_from_db()
        self.assertEqual(continuing_job.status, CrawlJob.Status.READY)

        with self.assertRaises(CrawlRunStateInvalid):
            complete_run(run, outcome=CrawlRun.Status.SUCCEEDED)

    def test_pause_and_manual_resume_with_same_account(self):
        self.make_account()
        job = self.make_job(allow_manual_resume=True)
        run = start_run(job)
        pause_run(run, reason=CrawlRun.PauseReason.MANUAL)
        run.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.PAUSED)
        self.assertEqual(run.pause_reason, CrawlRun.PauseReason.MANUAL)
        self.assertEqual(job.status, CrawlJob.Status.PAUSED)

        resumed = resume_run(run)
        self.assertEqual(resumed.status, CrawlRun.Status.RUNNING)
        self.assertEqual(resumed.account, run.account)

        no_resume_job = self.make_job(name="Locked job", allow_manual_resume=False)
        run2 = start_run(no_resume_job)
        pause_run(run2, reason=CrawlRun.PauseReason.MANUAL)
        with self.assertRaises(CrawlRunStateInvalid):
            resume_run(run2)

    def test_risk_control_pause_blocks_auto_resume(self):
        account = self.make_account()
        job = self.make_job()
        run = start_run(job)
        # Production flow: flagging the account pauses its running run.
        flag_account_risk_control(account, reason="Verification wall detected")
        run.refresh_from_db()
        self.assertEqual(run.pause_reason, CrawlRun.PauseReason.RISK_CONTROL)
        with self.assertRaises(RiskControlPaused):
            resume_run(run)
        with self.assertRaises(CrawlRunStateInvalid):
            pause_run(run, reason=CrawlRun.PauseReason.MANUAL)

    def test_cancel_closes_run_and_job_without_open_runs(self):
        self.make_account()
        job = self.make_job()
        run = start_run(job)
        cancel_run(run)
        run.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.CANCELED)
        self.assertEqual(job.status, CrawlJob.Status.CANCELED)
        with self.assertRaises(CrawlRunStateInvalid):
            cancel_run(run)


class CrawlerAccountTests(CrawlerControlTestBase):
    def test_session_storage_is_encrypted_and_rejects_passwords(self):
        account = create_crawler_account(label="Session account")
        record_account_session(account, {"joybuy_session": "abc123", "region": "GB"})
        account.refresh_from_db()
        self.assertNotIn("abc123", account.session_cipher)
        self.assertNotIn("joybuy_session", account.session_cipher)
        self.assertEqual(account.session_status, CrawlerAccount.SessionStatus.VALID)
        self.assertEqual(
            load_account_session(account),
            {"joybuy_session": "abc123", "region": "GB"},
        )

        with self.assertRaises(CrawlSessionSecretInvalid):
            record_account_session(account, {"facebook_password": "never"})
        with self.assertRaises(CrawlSessionSecretInvalid):
            record_account_session(account, {"PASSWD": "never"})

    def test_expired_session_blocks_account_selection(self):
        self.make_account()
        job = self.make_job()
        run = start_run(job)
        account = run.account
        mark_session_expired(account)

        other = create_crawler_account(label="Expired only", account_group="solo")
        record_account_session(other, {"joybuy_session": "t"})
        mark_session_expired(other)
        job2 = self.make_job(name="Solo group job", account_group="solo")
        with self.assertRaises(CrawlAccountStateInvalid):
            start_run(job2)

        record_account_session(account, {"joybuy_session": "refreshed"})
        account.refresh_from_db()
        self.assertEqual(account.session_status, CrawlerAccount.SessionStatus.VALID)
        self.assertEqual(
            load_account_session(account),
            {"joybuy_session": "refreshed"},
        )
        self.assertFalse(CrawlRun.objects.filter(pk=run.pk, account=None).exists())

    def test_risk_control_pauses_account_and_run_and_requires_manual_reactivation(self):
        account = self.make_account()
        job = self.make_job()
        run = start_run(job)

        flag_account_risk_control(account, reason="Verification wall detected")
        account.refresh_from_db()
        run.refresh_from_db()
        self.assertEqual(account.status, CrawlerAccount.Status.PAUSED_RISK_CONTROL)
        self.assertEqual(run.status, CrawlRun.Status.PAUSED)
        self.assertEqual(run.pause_reason, CrawlRun.PauseReason.RISK_CONTROL)
        self.assertFalse(account.is_selectable)

        same_group_job = self.make_job(name="Second job")
        with self.assertRaises(CrawlAccountStateInvalid):
            start_run(same_group_job)

        reactivate_account(account, note="Cleared by human review")
        account.refresh_from_db()
        self.assertEqual(account.status, CrawlerAccount.Status.ACTIVE)
        # After human review the SAME pinned run may resume; never another account.
        resumed = resume_run(run)
        self.assertEqual(resumed.status, CrawlRun.Status.RUNNING)
        self.assertEqual(resumed.account, account)
        fresh_run = start_run(same_group_job)
        self.assertEqual(fresh_run.account, account)
        self.assertNotEqual(fresh_run.pk, run.pk)


class RawResponseArchiveTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self._raw_tmp = tempfile.TemporaryDirectory(prefix="joybuy-raw-test-")
        self.addCleanup(self._raw_tmp.cleanup)
        override = override_settings(CRAWL_RAW_ROOT=Path(self._raw_tmp.name))
        override.enable()
        self.addCleanup(override.disable)
        self.make_account()
        self.job = self.make_job()
        self.run = start_run(self.job)

    def test_raw_response_is_gzipped_indexed_and_expires_in_30_days(self):
        crawled = timezone.now()
        payload = b"<html>product page</html>"
        row = record_raw_response(
            self.run,
            url="https://www.joybuy.test/product/1",
            status_code=200,
            content_type="text/html",
            payload=payload,
            crawled_at=crawled,
        )
        self.assertEqual(row.response_hash, hashlib.sha256(payload).hexdigest())
        self.assertEqual(row.byte_size, len(payload))
        self.assertEqual(
            row.expires_at,
            crawled + timedelta(days=settings.CRAWL_RAW_RETENTION_DAYS),
        )
        self.assertTrue(row.relative_path.startswith(f"{crawled.strftime('%Y/%m/%d')}/"))
        self.assertIn(str(self.run.public_id), row.relative_path)
        physical = resolve_raw_path(row.relative_path)
        self.assertTrue(physical.is_file())
        self.assertEqual(gzip.decompress(physical.read_bytes()), payload)

    def test_empty_payload_and_path_escapes_are_rejected(self):
        with self.assertRaises(RawResponseInvalid):
            record_raw_response(
                self.run,
                url="https://www.joybuy.test/x",
                status_code=200,
                payload=b"",
            )
        with self.assertRaises(RawResponseInvalid):
            resolve_raw_path("../../outside.gz")
        with self.assertRaises(RawResponseInvalid):
            redact_sensitive_keys(["not", "an", "object"])
        redacted = redact_sensitive_keys(
            {"url": "https://x", "cookie": "a=1", "Authorization": "Bearer t"}
        )
        self.assertEqual(redacted["url"], "https://x")
        self.assertEqual(redacted["cookie"], "[REDACTED]")
        self.assertEqual(redacted["Authorization"], "[REDACTED]")

    def test_purge_deletes_files_but_keeps_rows_and_hashes(self):
        crawled = timezone.now()
        expired_row = record_raw_response(
            self.run,
            url="https://www.joybuy.test/old",
            status_code=200,
            payload=b"old payload",
            crawled_at=crawled - timedelta(days=settings.CRAWL_RAW_RETENTION_DAYS + 1),
        )
        fresh_row = record_raw_response(
            self.run,
            url="https://www.joybuy.test/new",
            status_code=200,
            payload=b"fresh payload",
            crawled_at=crawled,
        )

        purged = purge_expired_raw_responses()
        self.assertEqual(purged, 1)
        expired_row.refresh_from_db()
        fresh_row.refresh_from_db()
        self.assertTrue(expired_row.file_deleted)
        self.assertIsNotNone(expired_row.deleted_at)
        self.assertNotEqual(expired_row.response_hash, "")
        self.assertFalse(resolve_raw_path(expired_row.relative_path).exists())
        self.assertFalse(fresh_row.file_deleted)
        self.assertTrue(resolve_raw_path(fresh_row.relative_path).exists())

        self.assertEqual(purge_expired_raw_responses(), 0)
