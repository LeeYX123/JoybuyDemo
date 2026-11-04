from datetime import timedelta

from catalog.product_services import get_or_create_spu_from_source
from django.test import TestCase
from django.utils import timezone
from media.models import MediaAsset
from media.storage import store_bytes
from media.tests.test_media_storage import IsolatedMediaRootMixin

from reviews.domain import (
    ReviewContentInvalid,
    ReviewerIdentityInvalid,
    ReviewSourceIdentityInvalid,
)
from reviews.models import Review, ReviewMedia, ReviewVersion, VirtualReviewer
from reviews.services import (
    attach_review_media,
    get_or_create_reviewer_from_source,
    mark_source_review_deleted,
    source_fingerprint,
    upsert_source_review,
)


class ReviewDomainTests(IsolatedMediaRootMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="review-spu-1",
            title="Reviewed product",
        )
        self.observed = timezone.now()

    def make_reviewer(self, stable_id="reviewer-1", **kwargs):
        return get_or_create_reviewer_from_source(
            source_system="joybuy",
            stable_public_identifier=stable_id,
            **kwargs,
        )

    def upsert(self, source_id="review-1", **kwargs):
        defaults = {
            "rating": 4,
            "title": "Great product",
            "body": "Works as expected.",
            "locale": "en-GB",
            "variant_text": "Colour: Red / Size: M",
            "likes_count": 7,
            "source_reviewed_at": self.observed - timedelta(days=2),
            "source_url": "https://example.test/reviews",
            "source_position": {"page": 1, "rank": 3},
            "guest_display_name": "Guest User",
            "observed_at": self.observed,
        }
        defaults.update(kwargs)
        return upsert_source_review(
            self.spu,
            source_system="joybuy",
            source_id=source_id,
            **defaults,
        )

    def test_fingerprint_is_deterministic_and_source_scoped(self):
        first = source_fingerprint("joybuy", "user-42")
        second = source_fingerprint("Joybuy", "user-42")
        other_system = source_fingerprint("other-market", "user-42")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other_system)
        self.assertNotIn("user-42", first)
        with self.assertRaises(ReviewerIdentityInvalid):
            source_fingerprint("joybuy", "   ")
        with self.assertRaises(ReviewerIdentityInvalid):
            source_fingerprint("", "user-42")

    def test_stable_identity_dedups_across_nickname_changes(self):
        first, first_created = self.make_reviewer(display_name="Nick A")
        same, same_created = self.make_reviewer(stable_id="reviewer-1", display_name="Nick B")
        same_id_other_source, _ = get_or_create_reviewer_from_source(
            source_system="other-market",
            stable_public_identifier="reviewer-1",
        )

        self.assertTrue(first_created)
        self.assertFalse(same_created)
        self.assertEqual(first, same)
        self.assertEqual(same.display_name, "Nick B")
        self.assertEqual(VirtualReviewer.objects.count(), 2)
        self.assertNotEqual(first.fingerprint, same_id_other_source.fingerprint)

    def test_reviews_without_stable_identity_never_merge_or_create_reviewers(self):
        first, _ = self.upsert(source_id="guest-1", guest_display_name="Chris")
        second, _ = self.upsert(source_id="guest-2", guest_display_name="Chris")

        self.assertEqual(first.guest_display_name, "Chris")
        self.assertEqual(second.guest_display_name, "Chris")
        self.assertIsNone(first.reviewer)
        self.assertIsNone(second.reviewer)
        self.assertNotEqual(first, second)
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(VirtualReviewer.objects.count(), 0)

    def test_review_import_is_idempotent_and_tracks_observations(self):
        review, created = self.upsert()
        same, same_created = self.upsert()

        self.assertTrue(created)
        self.assertFalse(same_created)
        self.assertEqual(review, same)
        self.assertEqual(Review.objects.count(), 1)
        self.assertEqual(ReviewVersion.objects.count(), 1)
        self.assertEqual(review.versions.first().change_kind, ReviewVersion.ChangeKind.CREATED)
        self.assertEqual(review.source_position, {"page": 1, "rank": 3})

    def test_source_edits_keep_version_history(self):
        review, _ = self.upsert(rating=5, body="Original body", observed_at=self.observed)
        edited_at = self.observed + timedelta(hours=6)
        edited, _ = self.upsert(
            rating=3,
            body="Edited body",
            likes_count=9,
            observed_at=edited_at,
        )

        self.assertEqual(review, edited)
        edited.refresh_from_db()
        self.assertEqual(edited.rating, 3)
        self.assertEqual(edited.body, "Edited body")
        self.assertEqual(ReviewVersion.objects.count(), 2)
        previous = ReviewVersion.objects.get(change_kind=ReviewVersion.ChangeKind.UPDATED)
        self.assertEqual(previous.rating, 5)
        self.assertEqual(previous.body, "Original body")
        self.assertEqual(previous.observed_at, edited_at)
        self.assertNotEqual(edited.content_hash, previous.content_hash)

    def test_source_deletion_soft_deletes_and_hides_from_default_listing(self):
        review, _ = self.upsert()
        mark_source_review_deleted(source_system="joybuy", source_id="review-1")

        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.DELETED)
        self.assertIsNotNone(review.deleted_at)
        self.assertFalse(Review.objects.filter(status=Review.Status.ACTIVE).exists())
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())
        self.assertEqual(
            ReviewVersion.objects.filter(
                review=review, change_kind=ReviewVersion.ChangeKind.DELETED
            ).count(),
            1,
        )
        # Body text remains preserved for history; storefront filters by status.
        self.assertEqual(review.body, "Works as expected.")

        # Re-appearance at the source restores visibility without a new
        # version row, because the content did not change.
        restored, _ = self.upsert(observed_at=self.observed + timedelta(days=1))
        restored.refresh_from_db()
        self.assertEqual(restored.status, Review.Status.ACTIVE)
        self.assertIsNone(restored.deleted_at)
        self.assertEqual(ReviewVersion.objects.filter(review=review).count(), 2)

    def test_source_identity_cannot_move_between_products(self):
        other_spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="review-spu-2",
            title="Another product",
        )
        self.upsert()
        with self.assertRaises(ReviewSourceIdentityInvalid):
            upsert_source_review(
                other_spu,
                source_system="joybuy",
                source_id="review-1",
                rating=3,
                guest_display_name="Guest",
            )

    def test_invalid_review_content_is_rejected(self):
        with self.assertRaises(ReviewContentInvalid):
            self.upsert(rating=0)
        with self.assertRaises(ReviewContentInvalid):
            self.upsert(rating=6)
        with self.assertRaises(ReviewContentInvalid):
            self.upsert(rating=True)
        with self.assertRaises(ReviewContentInvalid):
            self.upsert(title="x" * 301)
        with self.assertRaises(ReviewContentInvalid):
            self.upsert(guest_display_name="   ")
        with self.assertRaises(ReviewSourceIdentityInvalid):
            self.upsert(source_id="   ")
        self.assertEqual(Review.objects.count(), 0)

    def test_review_media_attachment_is_idempotent(self):
        review, _ = self.upsert()
        asset, _ = store_bytes(
            b"review-image-bytes",
            kind="REVIEW",
            mime_type="application/octet-stream",
        )
        first, first_created = attach_review_media(
            review, asset, media_kind="IMAGE", source_url="https://example.test/r.jpg", position=1
        )
        second, second_created = attach_review_media(review, asset, media_kind="IMAGE", position=2)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, second)
        self.assertEqual(second.position, 2)
        self.assertEqual(ReviewMedia.objects.count(), 1)
        with self.assertRaises(ReviewContentInvalid):
            attach_review_media(review, asset, media_kind="AUDIO")
        with self.assertRaises(ReviewContentInvalid):
            attach_review_media(review, None, media_kind="IMAGE")

    def test_identified_reviewer_reviews_link_to_reviewer_row(self):
        reviewer, created = self.make_reviewer(stable_id="reviewer-link", display_name="Alex")
        self.assertTrue(created)
        review, _ = self.upsert(reviewer=reviewer, guest_display_name="")
        self.assertEqual(review.reviewer, reviewer)
        self.assertEqual(review.reviewer.reviews.count(), 1)
        self.assertEqual(MediaAsset.objects.count(), 0)
