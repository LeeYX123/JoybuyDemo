import json

from django.test import TestCase
from django.urls import reverse

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from checkout.models import Address


class AddressApiTests(TestCase):
    def setUp(self):
        self.account, _ = BuyerAccount.objects.get_or_create(
            email="addresses@joybuy.test",
            defaults={"status": BuyerAccount.Status.ACTIVE},
        )
        token, _session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token
        self.url = reverse("address-list")

    def create(self, **overrides):
        payload = {
            "full_name": "Test Buyer",
            "phone": "+447000000001",
            "line1": "1 High Street",
            "city": "London",
            "postcode": "SW1A 1AA",
        }
        payload.update(overrides)
        return self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

    def test_create_makes_first_address_default_and_keeps_default_unique(self):
        first = self.create()
        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["is_default"])
        second = self.create(
            full_name="Second Buyer", line1="2 Low Street", postcode="EC1A 1BB"
        )
        self.assertEqual(second.status_code, 201)
        self.assertFalse(second.json()["is_default"])

        addresses = self.client.get(self.url).json()["addresses"]
        self.assertEqual(len(addresses), 2)
        self.assertEqual([row["is_default"] for row in addresses], [True, False])

        # Explicitly defaulting the second one moves the badge (never two).
        set_default = self.client.patch(
            self.url,
            data=json.dumps({"public_id": second.json()["public_id"], "is_default": True}),
            content_type="application/json",
        )
        self.assertEqual(set_default.status_code, 200)
        self.assertTrue(set_default.json()["is_default"])
        addresses = self.client.get(self.url).json()["addresses"]
        self.assertEqual(sum(1 for row in addresses if row["is_default"]), 1)
        self.assertTrue(addresses[0]["is_default"])
        self.assertEqual(addresses[0]["public_id"], second.json()["public_id"])

    def test_edit_updates_fields_and_can_take_over_default(self):
        first = self.create()
        second = self.create(full_name="Second Buyer", postcode="EC1A 1BB")
        edited = self.client.patch(
            self.url,
            data=json.dumps(
                {
                    "public_id": second.json()["public_id"],
                    "full_name": "Edited Buyer",
                    "phone": "+447000000002",
                    "line1": "22 Edited Road",
                    "line2": "Flat 4",
                    "city": "Manchester",
                    "county": "Greater Manchester",
                    "postcode": "M1 1AE",
                    "is_default": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(edited.status_code, 200)
        body = edited.json()
        self.assertEqual(body["full_name"], "Edited Buyer")
        self.assertEqual(body["city"], "Manchester")
        self.assertEqual(body["postcode"], "M1 1AE")
        self.assertTrue(body["is_default"])
        self.assertFalse(Address.objects.get(public_id=first.json()["public_id"]).is_default)

    def test_delete_default_promotes_remaining_address(self):
        first = self.create()
        second = self.create(full_name="Second Buyer", postcode="EC1A 1BB")
        deleted = self.client.delete(
            self.url,
            data=json.dumps({"public_id": first.json()["public_id"]}),
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["removed"])
        remaining = Address.objects.get(public_id=second.json()["public_id"])
        self.assertTrue(remaining.is_default)

    def test_validation_and_not_found(self):
        # 2026-11-28 邮编格式校验放开：任意内容（非空）都被接受。
        bad_postcode = self.create(postcode="12345")
        self.assertEqual(bad_postcode.status_code, 201)
        self.assertEqual(bad_postcode.json()["postcode"], "12345")

        missing = self.client.post(
            self.url,
            data=json.dumps({"full_name": "Only Name"}),
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"]["code"], "ADDRESS_INCOMPLETE")

        unknown = self.client.patch(
            self.url,
            data=json.dumps(
                {"public_id": "00000000-0000-0000-0000-000000000000", "is_default": True}
            ),
            content_type="application/json",
        )
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json()["error"]["code"], "ADDRESS_NOT_FOUND")

    def test_anonymous_is_rejected(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.create().status_code, 401)
