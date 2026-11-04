from catalog.models import Spu
from catalog.product_services import get_or_create_spu_from_source
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from media.storage import store_bytes

from reviews.import_services import import_sampled_reviews
from reviews.services import attach_review_media, mark_source_review_deleted


class ProductReviewsApiTests(TestCase):
    def setUp(self):
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="reviews-api-spu", title="Reviewed product"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.url = reverse("product-reviews", kwargs={"public_id": self.spu.public_id})

    def payload(self, index, rating=5, stable_id=None):
        return {
            "source_id": f"api-review-{index}",
            "rating": rating,
            "title": f"Review {index}",
            "body": f"Body of review {index}.",
            "reviewer_stable_id": stable_id or f"reviewer-{index}",
            "reviewer_name": f"User {index}",
            "position": {"rank": index},
        }

    def test_facets_pagination_and_reviewer_display(self):
        import_sampled_reviews(
            self.spu,
            [self.payload(1, 5), self.payload(2, 4), self.payload(3, 5)],
            source_system="joybuy",
        )
        response = self.client.get(self.url)
        data = response.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["distribution"], {"1": 0, "2": 0, "3": 0, "4": 1, "5": 2})
        self.assertTrue(data["average"].startswith("4.66"))
        self.assertEqual(len(data["items"]), 3)
        names = {item["display_name"] for item in data["items"]}
        self.assertEqual(names, {"User 1", "User 2", "User 3"})

        filtered = self.client.get(self.url, {"rating": "5"}).json()
        self.assertEqual(filtered["filtered_total"], 2)
        self.assertEqual(filtered["count"], 3, "Overall count is not filtered.")

        page_one = self.client.get(self.url, {"page": "1"}).json()
        self.assertEqual(page_one["page"], 1)

    def test_deleted_reviews_are_excluded_but_kept_in_history(self):
        import_sampled_reviews(
            self.spu,
            [self.payload(1), self.payload(2)],
            source_system="joybuy",
        )
        mark_source_review_deleted(source_system="joybuy", source_id="api-review-1")

        data = self.client.get(self.url).json()
        self.assertEqual(data["count"], 1)
        self.assertNotIn("Review 1", [item["title"] for item in data["items"]])
        self.assertEqual(data["distribution"]["5"], 1)

    def test_guest_display_name_shown_without_reviewer_row(self):
        from reviews.services import upsert_source_review

        upsert_source_review(
            self.spu,
            source_system="joybuy",
            source_id="api-review-guest",
            rating=3,
            guest_display_name="Anon Shopper",
        )
        data = self.client.get(self.url).json()
        self.assertEqual(data["items"][0]["display_name"], "Anon Shopper")
        self.assertEqual(
            data["items"][0]["public_id"],
            str(self.spu.reviews.get(source_id="api-review-guest").public_id),
        )

    def test_review_media_urls_are_local(self):
        import_sampled_reviews(self.spu, [self.payload(1)], source_system="joybuy")
        review = self.spu.reviews.get(source_id="api-review-1")
        asset, _ = store_bytes(b"review-photo-bytes", kind="REVIEW", mime_type="image/png")
        attach_review_media(review, asset, media_kind="IMAGE", observed_at=timezone.now())

        data = self.client.get(self.url).json()
        media = data["items"][0]["media"]
        self.assertEqual(len(media), 1)
        self.assertTrue(media[0]["url"].startswith("/media/reviews/"))

    def test_no_reviews_empty_state_and_invalid_filter(self):
        empty = self.client.get(self.url).json()
        self.assertEqual(empty["count"], 0)
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["total_pages"], 0)
        self.assertIsNone(empty["average"])

        bad = self.client.get(self.url, {"rating": "9"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "REVIEW_FILTER_INVALID")

    def test_unknown_product_returns_404(self):
        response = self.client.get(
            reverse(
                "product-reviews",
                kwargs={"public_id": "00000000-0000-0000-0000-000000000000"},
            )
        )
        self.assertEqual(response.status_code, 404)
