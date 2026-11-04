import sys
import unittest
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from catalog.product_services import get_or_create_spu_from_source  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402
from django.utils import timezone  # noqa: E402
from joybuy_crawler.sampling import SampleCandidate  # noqa: E402

from reviews.import_services import (  # noqa: E402
    import_sampled_reviews,
    ingest_review_candidates,
)
from reviews.models import Review, ReviewVersion, VirtualReviewer  # noqa: E402

SCRAPY_AVAILABLE = find_spec("scrapy") is not None
SEED = 42


def make_candidates(count: int, *, media_every: int = 5, base_position: int = 0):
    """Deterministic candidate pool: ratings weighted 5>4>3, recent first."""

    from datetime import datetime
    from datetime import timezone as dt_timezone

    candidates = []
    for index in range(count):
        rating = 5 if index % 2 == 0 else (4 if index % 3 == 0 else 3)
        candidates.append(
            SampleCandidate(
                source_id=f"review-{base_position + index:04d}",
                rating=rating,
                reviewed_at=datetime(2026, 11, 1, tzinfo=dt_timezone.utc) - timedelta(days=index),
                has_media=index % media_every == 0,
                position=base_position + index + 1,
            )
        )
    return candidates


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class StratifiedSamplingTests(unittest.TestCase):
    def test_target_below_total_keeps_rating_distribution(self):
        from joybuy_crawler.sampling import stratified_sample

        candidates = make_candidates(100)
        outcome = stratified_sample(candidates, target=50, seed=SEED)
        self.assertEqual(len(outcome.selected), 50)
        self.assertEqual(len(set(outcome.selected)), 50)

        strata = outcome.metadata["strata"]
        self.assertEqual(sum(item["selected"] for item in strata.values()), 50)
        # The pool only contains 3/4/5-star reviews (5: 50, 4: ~17, 3: rest);
        # quotas must follow that source distribution, not invent strata.
        self.assertEqual(set(strata), {"3", "4", "5"})
        self.assertGreater(strata["5"]["selected"], 20)
        self.assertEqual(strata["5"]["available"], 50)

    def test_media_reviews_are_preferred_within_each_stratum(self):
        from joybuy_crawler.sampling import stratified_sample

        candidates = [
            SampleCandidate(source_id=f"plain-{index}", rating=5, has_media=False, position=index)
            for index in range(20)
        ] + [
            SampleCandidate(
                source_id=f"media-{index}", rating=5, has_media=True, position=100 + index
            )
            for index in range(5)
        ]
        outcome = stratified_sample(candidates, target=10, seed=SEED)
        selected = set(outcome.selected)
        media_count = sum(1 for source_id in selected if source_id.startswith("media-"))
        self.assertEqual(
            media_count, 5, "All 5 media reviews of the stratum must be selected first."
        )

    def test_sampling_is_deterministic_for_a_given_seed(self):
        from joybuy_crawler.sampling import stratified_sample

        # Reviews sharing the same timestamp make the seed tiebreak matter.
        candidates = [
            SampleCandidate(
                source_id=f"tied-{index:03d}",
                rating=5,
                reviewed_at=datetime(2026, 10, 1, tzinfo=dt_timezone.utc),
                has_media=False,
                position=index + 1,
            )
            for index in range(20)
        ]
        first = stratified_sample(candidates, target=10, seed=SEED)
        second = stratified_sample(candidates, target=10, seed=SEED)
        different_seed = stratified_sample(candidates, target=10, seed=SEED + 1)

        self.assertEqual(first.selected, second.selected)
        self.assertNotEqual(first.selected, different_seed.selected)

    def test_small_pools_return_everything_and_single_digit_targets(self):
        from joybuy_crawler.sampling import stratified_sample

        candidates = make_candidates(7)
        outcome = stratified_sample(candidates, target=50, seed=SEED)
        self.assertEqual(len(outcome.selected), 7)
        self.assertEqual(outcome.metadata["strategy"], "all-available")

        single = stratified_sample(candidates, target=1, seed=SEED)
        self.assertEqual(len(single.selected), 1)

    def test_empty_pool_returns_empty_without_error(self):
        from joybuy_crawler.sampling import stratified_sample

        outcome = stratified_sample([], target=50, seed=SEED)
        self.assertEqual(outcome.selected, [])
        self.assertEqual(outcome.metadata["available"], 0)


class ReviewImportTests(CrawlerControlTestBase):
    """Sampling ingestion and review import through the WP-12 services."""

    def setUp(self):
        super().setUp()
        self.observed = timezone.now()
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="sampling-spu",
            title="Sampled product",
        )

    def payload(self, source_id, **kwargs):
        defaults = {
            "source_id": source_id,
            "rating": 4,
            "title": f"Review {source_id}",
            "body": "Body text.",
            "reviewed_at": self.observed - timedelta(days=3),
            "reviewer_stable_id": f"reviewer-{source_id}",
            "reviewer_name": f"User {source_id}",
            "position": {"page": 1, "rank": abs(hash(source_id)) % 50 + 1},
        }
        defaults.update(kwargs)
        return defaults

    def test_ingest_builds_candidates_with_media_flags(self):
        candidates = ingest_review_candidates(
            [
                {"source_id": "r1", "rating": 5, "image_urls": ["x.jpg"], "position": 1},
                {"source_id": "r2", "rating": 3, "position": 2},
                {"source_id": "", "rating": 2},
            ]
        )
        self.assertEqual(len(candidates), 2)
        self.assertTrue(candidates[0].has_media)
        self.assertFalse(candidates[1].has_media)
        self.assertEqual([item.position for item in candidates], [1, 2])

    def test_import_creates_reviewers_reviews_and_dedups_across_runs(self):
        payloads = [
            self.payload("rev-1"),
            self.payload("rev-2"),
            self.payload("rev-3"),
        ]
        result = import_sampled_reviews(
            self.spu, payloads, source_system="joybuy", observed_at=self.observed
        )
        self.assertEqual(len(result["imported"]), 3)
        self.assertEqual(result["errors"], [])
        self.assertEqual(Review.objects.count(), 3)
        self.assertEqual(VirtualReviewer.objects.count(), 3)

        # Same sample again: fully idempotent, no new rows.
        result_again = import_sampled_reviews(
            self.spu, payloads, source_system="joybuy", observed_at=self.observed
        )
        self.assertTrue(all(not item["created"] for item in result_again["imported"]))
        self.assertEqual(Review.objects.count(), 3)
        self.assertEqual(VirtualReviewer.objects.count(), 3)
        self.assertEqual(result_again["soft_deleted"], [])

    def test_reviews_without_stable_identity_stay_guests(self):
        payloads = [
            self.payload("guest-1", reviewer_stable_id=""),
            self.payload("guest-2", reviewer_stable_id="", reviewer_name="Same Nick"),
        ]
        result = import_sampled_reviews(
            self.spu, payloads, source_system="joybuy", observed_at=self.observed
        )
        self.assertEqual(len(result["imported"]), 2)
        self.assertEqual(VirtualReviewer.objects.count(), 0)
        for review in Review.objects.all():
            self.assertIsNone(review.reviewer)
            self.assertTrue(review.guest_display_name)

    def test_disappearing_reviews_are_soft_deleted_and_can_reappear(self):
        payloads = [self.payload("keep-1"), self.payload("drop-1")]
        import_sampled_reviews(
            self.spu, payloads, source_system="joybuy", observed_at=self.observed
        )
        self.assertEqual(Review.objects.filter(status=Review.Status.ACTIVE).count(), 2)

        # Next window no longer contains drop-1.
        result = import_sampled_reviews(
            self.spu, [self.payload("keep-1")], source_system="joybuy", observed_at=self.observed
        )
        self.assertEqual(result["soft_deleted"], ["drop-1"])
        drop = Review.objects.get(source_id="drop-1")
        self.assertEqual(drop.status, Review.Status.DELETED)
        self.assertIsNotNone(drop.deleted_at)
        self.assertTrue(ReviewVersion.objects.filter(review=drop).exists())

        # It reappears in a later window and becomes visible again.
        import_sampled_reviews(
            self.spu,
            [self.payload("keep-1"), self.payload("drop-1")],
            source_system="joybuy",
            observed_at=self.observed + timedelta(hours=6),
        )
        drop.refresh_from_db()
        self.assertEqual(drop.status, Review.Status.ACTIVE)

    def test_invalid_payloads_are_reported_without_blocking_the_batch(self):
        payloads = [
            self.payload("good-1"),
            self.payload("bad-rating", rating=9),
            {"source_id": "missing-rating"},
        ]
        result = import_sampled_reviews(
            self.spu, payloads, source_system="joybuy", observed_at=self.observed
        )
        self.assertEqual(len(result["imported"]), 1)
        self.assertEqual(
            {item["source_id"] for item in result["errors"]},
            {"bad-rating", "missing-rating"},
        )
        self.assertEqual(Review.objects.count(), 1)

    def test_import_respects_job_review_target_bounds(self):
        from crawler_control.domain import CrawlJobParamsInvalid
        from crawler_control.services import create_crawl_job

        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Bad review target",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                review_target=500,
            )
