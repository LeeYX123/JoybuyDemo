from audit.models import AuditLog
from django.test import TestCase
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market
from offers.services import import_offer_from_source

from catalog.domain import FieldValueInvalid
from catalog.models import (
    LocalFieldOverride,
    LocalFieldOverrideVersion,
    SpuTranslation,
)
from catalog.override_services import (
    apply_source_field_values,
    clear_local_override,
    list_override_diffs,
    mark_source_fields_missing,
    propose_local_override,
    resolve_effective_value,
    review_local_override,
)
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source


class FieldOverrideLayerTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.merchant = get_import_fallback_merchant()
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="override-spu-1",
            title="Imported title",
        )
        self.translation = SpuTranslation.objects.get(spu=self.spu)

    def import_offer(self, sku_source_id="override-sku-1"):
        spu2, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="override-offer-spu",
            title="Offer product",
        )
        sku, _ = get_or_create_sku_from_source(
            spu=spu2,
            source_system="joybuy",
            source_id=sku_source_id,
            specification={},
        )
        offer, _ = import_offer_from_source(
            sku=sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id="override-offer-1",
            current_price="19.99",
            list_price="24.99",
        )
        return offer

    def approve_override(self, target, field_code, value):
        propose_local_override(
            target,
            field_code,
            value,
            reason="Fix source content",
            proposed_by=None,
        )
        return review_local_override(
            target,
            field_code,
            LocalFieldOverride.Status.APPROVED,
            reason="Reviewed and correct",
            reviewed_by=None,
        )

    def test_crawler_updates_never_shadow_approved_overrides(self):
        apply_source_field_values(
            self.translation, {"title": "Source title A"}, source_system="joybuy"
        )
        self.approve_override(self.translation, "title", "Local title")
        apply_source_field_values(
            self.translation, {"title": "Crawler changed title"}, source_system="joybuy"
        )

        resolved = resolve_effective_value(self.translation, "title")
        self.assertEqual(resolved["effective"], "Local title")
        self.assertEqual(resolved["effective_origin"], "local_override")
        self.assertEqual(resolved["source"], "Crawler changed title")

    def test_clearing_override_restores_following_source(self):
        apply_source_field_values(
            self.translation, {"title": "Source title"}, source_system="joybuy"
        )
        override = self.approve_override(self.translation, "title", "Local title")
        clear_local_override(self.translation, "title", reason="Override no longer needed")

        override.refresh_from_db()
        self.assertEqual(override.status, LocalFieldOverride.Status.CLEARED)
        resolved = resolve_effective_value(self.translation, "title")
        self.assertEqual(resolved["effective"], "Source title")
        self.assertEqual(resolved["effective_origin"], "source")

    def test_pending_rejected_and_cleared_overrides_do_not_shadow_source(self):
        apply_source_field_values(
            self.translation, {"title": "Source title"}, source_system="joybuy"
        )
        propose_local_override(self.translation, "title", "Pending title", reason="Needs review")
        self.assertEqual(
            resolve_effective_value(self.translation, "title")["effective"],
            "Source title",
        )

        review_local_override(
            self.translation,
            "title",
            LocalFieldOverride.Status.REJECTED,
            reason="Incorrect",
        )
        self.assertEqual(
            resolve_effective_value(self.translation, "title")["effective"],
            "Source title",
        )

        self.approve_override(self.translation, "title", "Approved title")
        clear_local_override(self.translation, "title", reason="Done")
        self.assertEqual(
            resolve_effective_value(self.translation, "title")["effective"],
            "Source title",
        )

    def test_override_lifecycle_writes_versions_and_audit_entries(self):
        propose_local_override(self.translation, "title", "Draft", reason="First proposal")
        override = review_local_override(
            self.translation,
            "title",
            LocalFieldOverride.Status.APPROVED,
            reason="Looks good",
        )

        self.assertEqual(override.version, 2)
        versions = list(override.versions.order_by("version"))
        self.assertEqual(
            [item.change_kind for item in versions],
            [
                LocalFieldOverrideVersion.ChangeKind.CREATE,
                LocalFieldOverrideVersion.ChangeKind.REVIEW,
            ],
        )
        self.assertEqual(versions[0].value, "Draft")
        self.assertEqual(versions[1].status, LocalFieldOverride.Status.APPROVED)

        actions = list(
            AuditLog.objects.filter(action__startswith="catalog.override.").order_by("created_at")
        )
        self.assertEqual(
            [item.action for item in actions],
            ["catalog.override.propose", "catalog.override.approve"],
        )
        self.assertEqual(actions[0].before_state, {})
        self.assertEqual(actions[0].after_state["status"], LocalFieldOverride.Status.PENDING)
        self.assertEqual(actions[1].before_state["status"], LocalFieldOverride.Status.PENDING)
        self.assertEqual(actions[1].after_state["status"], LocalFieldOverride.Status.APPROVED)
        self.assertEqual(actions[1].reason, "Looks good")

    def test_source_updates_are_idempotent_and_track_observations(self):
        first = apply_source_field_values(
            self.translation,
            {"title": "Same title", "subtitle": ""},
            source_system="joybuy",
        )
        second = apply_source_field_values(
            self.translation,
            {"title": "Same title", "subtitle": ""},
            source_system="Joybuy",
        )
        self.assertEqual(first, {"title": "Same title", "subtitle": ""})
        self.assertEqual(first, second)
        row = resolve_effective_value(self.translation, "title")
        self.assertEqual(row["source"], "Same title")

    def test_missing_source_fields_stop_shadowing_until_source_returns(self):
        apply_source_field_values(
            self.translation,
            {"title": "Title", "subtitle": "Sub"},
            source_system="joybuy",
        )
        marked = mark_source_fields_missing(self.translation, ["subtitle"], observed_at=None)
        self.assertEqual(marked, 1)
        subtitle = resolve_effective_value(self.translation, "subtitle")
        self.assertTrue(subtitle["source_is_missing"])
        self.assertIsNone(subtitle["effective"])

        apply_source_field_values(
            self.translation, {"subtitle": "Sub is back"}, source_system="joybuy"
        )
        subtitle = resolve_effective_value(self.translation, "subtitle")
        self.assertFalse(subtitle["source_is_missing"])
        self.assertEqual(subtitle["effective"], "Sub is back")

    def test_unknown_fields_and_invalid_values_are_rejected(self):
        with self.assertRaises(FieldValueInvalid):
            apply_source_field_values(
                self.translation, {"not_a_field": "x"}, source_system="joybuy"
            )
        with self.assertRaises(FieldValueInvalid):
            apply_source_field_values(self.translation, {"title": ""}, source_system="joybuy")
        with self.assertRaises(FieldValueInvalid):
            apply_source_field_values(self.translation, {"title": 12.5}, source_system="joybuy")
        with self.assertRaises(FieldValueInvalid):
            propose_local_override(self.translation, "title", "x", reason="   ")

    def test_offer_money_overrides_are_decimal_validated(self):
        offer = self.import_offer()
        apply_source_field_values(
            offer,
            {"current_price": "21.50", "promotion_label": "Spring sale"},
            source_system="joybuy",
        )
        self.approve_override(offer, "current_price", "18.00")

        resolved = resolve_effective_value(offer, "current_price")
        self.assertEqual(resolved["effective"], "18.00")
        self.assertEqual(resolved["effective_origin"], "local_override")

        with self.assertRaises(FieldValueInvalid):
            apply_source_field_values(offer, {"current_price": 19.99}, source_system="joybuy")
        with self.assertRaises(FieldValueInvalid):
            apply_source_field_values(offer, {"current_price": "19.999"}, source_system="joybuy")
        with self.assertRaises(FieldValueInvalid):
            apply_source_field_values(offer, {"current_price": "-1.00"}, source_system="joybuy")

    def test_reproposing_requires_review_again_and_versions_accumulate(self):
        apply_source_field_values(
            self.translation, {"title": "Source title"}, source_system="joybuy"
        )
        self.approve_override(self.translation, "title", "First")
        propose_local_override(self.translation, "title", "Second draft", reason="Update copy")

        override = LocalFieldOverride.objects.get()
        self.assertEqual(override.status, LocalFieldOverride.Status.PENDING)
        self.assertEqual(override.version, 3)
        self.assertEqual(
            resolve_effective_value(self.translation, "title")["effective"],
            "Source title",
        )
        self.assertEqual(override.versions.count(), 3)
        self.assertEqual(
            [item.change_kind for item in override.versions.order_by("version")],
            [
                LocalFieldOverrideVersion.ChangeKind.CREATE,
                LocalFieldOverrideVersion.ChangeKind.REVIEW,
                LocalFieldOverrideVersion.ChangeKind.UPDATE,
            ],
        )

    def test_diff_listing_reports_source_override_and_effective(self):
        apply_source_field_values(
            self.translation,
            {"title": "Source title", "description": "Source description"},
            source_system="joybuy",
        )
        self.approve_override(self.translation, "title", "Local title")
        diffs = {item["field"]: item for item in list_override_diffs(self.translation)}

        self.assertTrue(diffs["title"]["differs"])
        self.assertEqual(diffs["title"]["effective"], "Local title")
        self.assertFalse(diffs["description"]["differs"])
        self.assertEqual(diffs["description"]["effective"], "Source description")
        self.assertIsNone(diffs["subtitle"]["effective"])
        self.assertEqual(diffs["subtitle"]["effective_origin"], "none")
