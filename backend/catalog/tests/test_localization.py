from django.test import TestCase
from django.urls import reverse

from catalog.localization_services import (
    direct_translate_specification,
    translate_sku_specification,
)
from catalog.models import Spu, SpuMarketContent
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from catalog.search_services import rebuild_search_document
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Locale, Market
from offers.services import import_offer_from_source


class EuropeanMarketConfigurationTests(TestCase):
    def test_supported_markets_locales_and_display_symbol_are_seeded(self):
        response = self.client.get(reverse("storefront-markets"))
        self.assertEqual(response.status_code, 200)
        by_code = {item["code"]: item for item in response.json()["markets"]}
        self.assertEqual(set(by_code), {"BE", "DE", "FR", "GB", "LU", "NL"})
        self.assertEqual(by_code["DE"]["display_currency_symbol"], "$")
        self.assertEqual(by_code["DE"]["stored_currency"], "EUR")
        self.assertEqual(by_code["DE"]["offer_fallback_market"], "GB")
        self.assertEqual(
            {item["code"] for item in by_code["BE"]["locales"]},
            {"nl-BE", "fr-BE", "de-BE"},
        )
        self.assertEqual(
            {item["code"] for item in by_code["LU"]["locales"]},
            {"lb-LU", "fr-LU", "de-LU"},
        )


class ProductLocalizationTests(TestCase):
    def setUp(self):
        self.merchant = get_import_fallback_merchant()
        self.gb = Market.objects.get(code="GB")
        self.de = Market.objects.get(code="DE")
        self.gbp = Currency.objects.get(code="GBP")
        self.de_locale = Locale.objects.get(code="de-DE")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="localized-spu",
            title="Wireless Earbuds",
            locale="en-GB",
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.spu.refresh_from_db()
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="localized-sku",
            specification={"Colour": "Black", "Size": "Large", "Capacity": "256 GB"},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.gb,
            currency=self.gbp,
            source_system="joybuy",
            source_id="localized-offer",
            current_price="19.99",
        )
        self.offer.status = self.offer.Status.ACTIVE
        self.offer.save(update_fields=["status", "updated_at"])

    def test_direct_spec_translation_preserves_numbers_and_flags_unknown_terms(self):
        translated, untranslated = direct_translate_specification(
            {"Colour": "Black", "Capacity": "256 GB", "Finish": "Matte"},
            self.de_locale,
        )
        self.assertEqual(translated["Farbe"], "Schwarz")
        self.assertEqual(translated["Kapazität"], "256 GB")
        self.assertEqual(translated["Finish"], "Matte")
        self.assertEqual(untranslated, ["Finish", "Matte"])

    def test_detail_uses_market_content_translated_specs_and_unconverted_gb_price(self):
        SpuMarketContent.objects.create(
            spu=self.spu,
            market=self.de,
            locale=self.de_locale,
            title="Kabellose Ohrhörer",
            description="Deutsche Produktbeschreibung",
            actual_locales={"title": "de-DE", "description": "de-DE"},
            origin=SpuMarketContent.Origin.HUMAN,
        )
        translation = translate_sku_specification(self.sku, self.de_locale)
        self.assertFalse(translation.needs_review)

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id}),
            {"market": "DE", "locale": "de-DE"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["market"], "DE")
        self.assertEqual(data["requested_locale"], "de-DE")
        self.assertEqual(data["title"], "Kabellose Ohrhörer")
        self.assertEqual(data["skus"][0]["specification"]["Farbe"], "Schwarz")
        self.assertEqual(data["skus"][0]["canonical_specification"]["Colour"], "Black")
        self.assertTrue(data["skus"][0]["specification_translated"])
        self.assertEqual(data["skus"][0]["offer"]["price"], "19.9900")
        self.assertEqual(data["skus"][0]["offer"]["price_source_market"], "GB")
        self.assertEqual(data["skus"][0]["offer"]["display_currency_symbol"], "$")

    def test_search_documents_are_separate_by_market_and_locale(self):
        SpuMarketContent.objects.create(
            spu=self.spu,
            market=self.gb,
            locale=self.de_locale,
            title="Kopfhörer",
            origin=SpuMarketContent.Origin.HUMAN,
        )
        english = rebuild_search_document(self.spu, market=self.gb, locale_code="en-GB")
        german = rebuild_search_document(self.spu, market=self.gb, locale_code="de-DE")
        self.assertNotEqual(english.pk, german.pk)
        self.assertEqual(english.title, "Wireless Earbuds")
        self.assertEqual(german.title, "Kopfhörer")
