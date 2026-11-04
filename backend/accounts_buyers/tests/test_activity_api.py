import time

from catalog.models import Spu
from catalog.product_services import get_or_create_spu_from_source
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, Favourite, RecentlyViewed


class ActivityApiTests(TestCase):
    def setUp(self):
        self.account, _ = BuyerAccount.objects.get_or_create(
            email="activity@joybuy.test",
            defaults={"status": BuyerAccount.Status.ACTIVE},
        )
        # Create a real session token so the middleware authenticates.
        from accounts_buyers.services import create_buyer_session

        token, _session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test-agent"
        )
        self.client.cookies["joybuy_buyer_session"] = token

        self.spu_a, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="act-a", title="Product A"
        )
        self.spu_b, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="act-b", title="Product B"
        )
        Spu.objects.filter(pk__in=[self.spu_a.pk, self.spu_b.pk]).update(status=Spu.Status.ACTIVE)
        self.fav_url = reverse("buyer-favourites")
        self.recent_url = reverse("buyer-recently-viewed")

    def test_favourite_add_list_remove_flow(self):
        response = self.client.post(
            self.fav_url,
            data=f'{{"spu_public_id": "{self.spu_a.public_id}"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["added"])

        # Adding again is idempotent.
        response = self.client.post(
            self.fav_url,
            data=f'{{"spu_public_id": "{self.spu_a.public_id}"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["added"])

        listed = self.client.get(self.fav_url).json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["title"], "Product A")

        removed = self.client.delete(
            self.fav_url,
            data=f'{{"spu_public_id": "{self.spu_a.public_id}"}}',
            content_type="application/json",
        ).json()
        self.assertTrue(removed["removed"])
        self.assertEqual(self.client.get(self.fav_url).json()["total"], 0)

    def test_recently_viewed_records_and_bumps_without_duplicates(self):
        self.client.get(reverse("product-detail", kwargs={"public_id": self.spu_a.public_id}))
        time.sleep(0.01)
        self.client.get(reverse("product-detail", kwargs={"public_id": self.spu_b.public_id}))
        # Viewing A again bumps it to the front instead of duplicating.
        time.sleep(0.01)
        self.client.get(reverse("product-detail", kwargs={"public_id": self.spu_a.public_id}))

        data = self.client.get(self.recent_url).json()
        titles = [item["title"] for item in data["items"]]
        self.assertEqual(titles, ["Product A", "Product B"])

        cleared = self.client.delete(self.recent_url).json()
        self.assertTrue(cleared["cleared"])
        self.assertEqual(self.client.get(self.recent_url).json()["total"], 0)

    def test_anonymous_requests_require_sign_in(self):
        self.client.cookies.clear()
        for url in (self.fav_url, self.recent_url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_unknown_product_in_favourite_returns_404(self):
        response = self.client.post(
            self.fav_url,
            data='{"spu_public_id": "00000000-0000-0000-0000-000000000000"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        _ = RecentlyViewed, Favourite, timezone
