import sys
from datetime import timedelta
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.utils import timezone  # noqa: E402

from catalog.override_services import resolve_effective_value  # noqa: E402
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source  # noqa: E402
from crawler_control.domain import CrawlerControlError  # noqa: E402
from crawler_control.import_services import import_staging_product  # noqa: E402
from crawler_control.models import (  # noqa: E402
    CrawlJob,
    QualityGateReport,
    StagingProduct,
)
from crawler_control.quality_services import (  # noqa: E402
    clear_stale_suspicions,
    evaluate_batch_quality,
    mark_missing_offers_suspect,
    report_account_risk,
    requeue_staging_for_replay,
    reset_circuit_breaker,
)
from crawler_control.services import (  # noqa: E402
    flag_account_risk_control,
    reactivate_account,
    start_run,
)
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402
from merchants.services import get_import_fallback_merchant  # noqa: E402
from offers.models import Offer  # noqa: E402
from offers.services import import_offer_from_source  # noqa: E402


class QualityGateTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Gate job")
        self.run = start_run(self.job)

    def good_payload(self, source_id):
        return {
            "source_id": source_id,
            "title": "Good product",
            "currency": "GBP",
            "current_price": "9.99",
            "skus": [{"source_id": "s1", "specs": [], "price": "9.99"}],
        }

    def bad_payloads(self, count):
        return [
            {
                "source_id": f"bad-{index}",
                "title": "",
                "currency": "",
                "current_price": None,
                "skus": [],
            }
            for index in range(count)
        ]

    def test_failed_batch_never_touches_imported_data(self):
        from joybuy_crawler.ingest import ingest_product_payload

        # Good data lands first.
        good_staging = ingest_product_payload(
            self.run,
            self.good_payload("good-1"),
            source_system="joybuy",
            parser_version="p1",
            structure_version=1,
        )
        import_staging_product(good_staging, market=self.market, currency=self.currency)
        offer_count = Offer.objects.count()

        # An anomalous batch arrives through the same run.
        bad_staging = ingest_product_payload(
            self.run,
            self.bad_payloads(1)[0],
            source_system="joybuy",
            source_url="https://fixture.test/p/bad",
            parser_version="p1",
            structure_version=1,
        )
        report = evaluate_batch_quality(
            self.run,
            page_type="product_detail",
            structure_version=1,
            payloads=[self.good_payload("ok-1"), *self.bad_payloads(5)],
        )
        self.assertEqual(report.status, QualityGateReport.Status.FAILED)
        self.assertTrue(report.paused_job)
        self.assertIn("current_price", report.failure_detail)

        # The rejected row is NOT imported and existing data is untouched.
        self.assertEqual(Offer.objects.count(), offer_count)
        bad_staging.refresh_from_db()
        self.assertEqual(bad_staging.status, StagingProduct.Status.PENDING)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CrawlJob.Status.PAUSED)

    def test_missing_rate_thresholds_are_enforced_per_field(self):
        report = evaluate_batch_quality(
            self.run,
            page_type="product_detail",
            structure_version=1,
            payloads=[
                self.good_payload("a"),
                self.good_payload("b"),
                self.good_payload("c"),
                self.bad_payloads(1)[0],
            ],
            thresholds={"title": 0.30, "current_price": 0.10},
        )
        self.assertEqual(report.status, QualityGateReport.Status.FAILED)
        self.assertIn("current_price", report.failure_detail)
        self.assertNotIn("title", report.failure_detail)

        passing = evaluate_batch_quality(
            self.run,
            page_type="product_detail",
            structure_version=1,
            payloads=[self.good_payload("a"), self.good_payload("b")],
        )
        self.assertEqual(passing.status, QualityGateReport.Status.PASSED)
        self.assertFalse(passing.paused_job)

    def test_empty_batch_and_invalid_inputs_are_rejected(self):
        empty = evaluate_batch_quality(
            self.run, page_type="listing", structure_version=1, payloads=[]
        )
        self.assertEqual(empty.status, QualityGateReport.Status.FAILED)
        with self.assertRaises(CrawlerControlError):
            evaluate_batch_quality(self.run, page_type="unknown", structure_version=1, payloads=[])
        with self.assertRaises(CrawlerControlError):
            evaluate_batch_quality(
                self.run,
                page_type="listing",
                structure_version=1,
                payloads=[],
                thresholds={"source_url": 1.5},
            )

    def test_continue_failure_strategy_does_not_pause(self):
        self.job.failure_strategy = CrawlJob.FailureStrategy.CONTINUE
        self.job.save(update_fields=["failure_strategy"])
        report = evaluate_batch_quality(
            self.run,
            page_type="product_detail",
            structure_version=1,
            payloads=self.bad_payloads(3),
        )
        self.assertEqual(report.status, QualityGateReport.Status.FAILED)
        self.assertFalse(report.paused_job)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "RUNNING")


class StalenessTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.merchant = get_import_fallback_merchant()
        self.make_account()
        self.full_job = self.make_job(name="Full refresh", sync_mode=CrawlJob.SyncMode.FULL_REFRESH)
        self.run = start_run(self.full_job)

    def seed_offer(self, source_id, sku_source_id):
        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id=source_id, title=f"Product {source_id}"
        )
        sku, _ = get_or_create_sku_from_source(
            spu=spu, source_system="joybuy", source_id=sku_source_id, specification={}
        )
        offer, _ = import_offer_from_source(
            sku=sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id=source_id,
            current_price="5.00",
        )
        return offer

    def test_full_refresh_marks_unseen_offers_and_confirms_stale(self):
        seen = self.seed_offer("stale-seen", "sku-seen")
        unseen = self.seed_offer("stale-unseen", "sku-unseen")

        first = mark_missing_offers_suspect(self.run, seen_source_ids={"stale-seen"})
        self.assertEqual(first["marked_suspect"], 1)
        unseen.refresh_from_db()
        self.assertIsNotNone(unseen.suspected_stale_since)
        self.assertEqual(unseen.stale_confirmations, 1)
        self.assertNotEqual(unseen.source_availability, Offer.SourceAvailability.UNAVAILABLE)

        # Second consecutive miss confirms: UNAVAILABLE.
        mark_missing_offers_suspect(self.run, seen_source_ids={"stale-seen"})
        unseen.refresh_from_db()
        self.assertEqual(unseen.source_availability, Offer.SourceAvailability.UNAVAILABLE)
        seen.refresh_from_db()
        self.assertIsNone(seen.suspected_stale_since)

    def test_reappearing_offers_are_cleared_immediately(self):
        offer = self.seed_offer("comeback", "sku-comeback")
        mark_missing_offers_suspect(self.run, seen_source_ids=set())
        offer.refresh_from_db()
        self.assertIsNotNone(offer.suspected_stale_since)

        cleared = clear_stale_suspicions(self.run, seen_source_ids={"comeback"})
        self.assertEqual(cleared, 1)
        offer.refresh_from_db()
        self.assertIsNone(offer.suspected_stale_since)
        self.assertEqual(offer.stale_confirmations, 0)

    def test_incremental_sync_never_marks_staleness(self):
        incremental = self.make_job(name="Incremental", sync_mode=CrawlJob.SyncMode.INCREMENTAL)
        run = start_run(incremental)
        self.seed_offer("inc-offer", "inc-sku")
        with self.assertRaises(Exception):
            mark_missing_offers_suspect(run, seen_source_ids=set())


class CircuitBreakerTests(CrawlerControlTestBase):
    def test_two_accounts_in_window_trip_the_global_breaker(self):
        account_a = self.make_account(label="Breaker A")
        job_a = self.make_job(name="Job A")
        start_run(job_a)
        flag_account_risk_control(account_a, reason="Captcha wall")
        breaker_state = report_account_risk(account_a, reason="Captcha wall")
        self.assertFalse(breaker_state["tripped"])

        account_b = self.make_account(label="Breaker B")
        job_b = self.make_job(name="Job B")
        start_run(job_b)
        flag_account_risk_control(account_b, reason="Captcha wall")

        # Both accounts flagged inside the window: breaker trips, all jobs pause.
        with self.assertRaises(CrawlerControlError):
            start_run(self.make_job(name="Job C"))

        job_a.refresh_from_db()
        job_b.refresh_from_db()
        self.assertEqual(job_a.status, CrawlJob.Status.PAUSED)
        self.assertEqual(job_b.status, CrawlJob.Status.PAUSED)

        # Human reset is required; jobs stay paused until accounts are
        # reviewed and reactivated.
        reset_circuit_breaker(reason="Reviewed: source site outage, not abuse")
        reactivate_account(account_a, note="Cleared by ops")
        job_c = self.make_job(name="Job after reset")
        run_c = start_run(job_c)
        self.assertEqual(run_c.status, "RUNNING")
        self.assertEqual(run_c.account, account_a)

    def test_hits_spread_across_windows_do_not_trip(self):
        # First hit two hours ago, second hit now: the window never holds
        # two accounts at once, so the breaker stays closed.
        reset_circuit_breaker(reason="baseline")
        account_a = self.make_account(label="Old hit A")
        start_run(self.make_job(name="Old job A"))
        stale_time = timezone.now() - timedelta(hours=2)
        flag_account_risk_control(account_a, reason="Historic", observed_at=stale_time)

        account_b = self.make_account(label="Recent hit B")
        start_run(self.make_job(name="Old job B"))
        flag_account_risk_control(account_b, reason="Recent")

        state = report_account_risk(account_b, reason="Recent")
        self.assertFalse(state["tripped"])

    def test_reset_requires_a_reason(self):
        with self.assertRaises(CrawlerControlError):
            reset_circuit_breaker(reason="  ")

    def test_reactivation_after_review_allows_new_runs(self):
        account = self.make_account(label="Reactivate me")
        second = self.make_account(group="default", label="Second risk hit")
        job = self.make_job(name="Reactivate job")
        start_run(job)
        # The breaker trips at 2 distinct risk-controlled accounts in a
        # window; unauthenticated starts (2026-11-05) are unaffected, so
        # both accounts must be flagged for a genuine trip.
        flag_account_risk_control(account, reason="Suspicious pace")
        flag_account_risk_control(second, reason="Suspicious pace")
        with self.assertRaises(CrawlerControlError):
            start_run(self.make_job(name="Blocked while tripped"))
        reset_circuit_breaker(reason="Cleared by ops")
        reactivate_account(account, note="Verified manually")
        new_run = start_run(job)
        self.assertEqual(new_run.account, account)


class ReplayTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.make_account()
        self.run = start_run(self.make_job(name="Replay job"))

    def test_rejected_staging_row_can_be_requeued_and_imported(self):
        from joybuy_crawler.ingest import ingest_product_payload

        broken = ingest_product_payload(
            self.run,
            {
                "source_id": "replay-1",
                "title": "x",
                "currency": "GBP",
                "current_price": None,
                "skus": [],
            },
            source_system="joybuy",
            source_url="https://fixture.test/p/replay",
            parser_version="p1",
            structure_version=1,
        )
        with self.assertRaises(Exception):
            import_staging_product(broken, market=self.market, currency=self.currency)
        broken.refresh_from_db()
        self.assertEqual(broken.status, StagingProduct.Status.REJECTED)

        requeued = requeue_staging_for_replay(broken, note="parser v2 fixed price extraction")
        self.assertEqual(requeued.status, StagingProduct.Status.PENDING)

        # Parser "fixed": the payload now carries the price.
        from joybuy_crawler.ingest import ingest_product_payload

        fixed = ingest_product_payload(
            self.run,
            {
                "source_id": "replay-1",
                "title": "Replayed product",
                "currency": "GBP",
                "current_price": "3.99",
                "skus": [{"source_id": "s", "specs": [], "price": "3.99"}],
            },
            source_system="joybuy",
            source_url="https://fixture.test/p/replay",
            parser_version="p2",
            structure_version=1,
        )
        outcome = import_staging_product(fixed, market=self.market, currency=self.currency)
        self.assertEqual(outcome.staging.status, StagingProduct.Status.IMPORTED)
        self.assertEqual(Offer.objects.count(), 1)

        with self.assertRaises(CrawlerControlError):
            requeue_staging_for_replay(fixed)

    def test_imported_values_still_follow_the_two_layer_rules(self):
        from joybuy_crawler.ingest import ingest_product_payload

        staging = ingest_product_payload(
            self.run,
            {
                "source_id": "layer-1",
                "title": "Layered product",
                "currency": "GBP",
                "current_price": "7.77",
                "skus": [{"source_id": "s", "specs": [], "price": "7.77"}],
            },
            source_system="joybuy",
            source_url="https://fixture.test/p/layer",
            parser_version="p1",
            structure_version=1,
        )
        outcome = import_staging_product(staging, market=self.market, currency=self.currency)
        translation = outcome.spu.translations.get()
        resolved = resolve_effective_value(translation, "title")
        self.assertEqual(resolved["effective"], "Layered product")
        self.assertEqual(resolved["effective_origin"], "source")
