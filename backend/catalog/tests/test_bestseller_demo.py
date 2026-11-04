from django.core.management import call_command
from django.test import TestCase

from catalog.models import ProductSearchDocument, SpuSourceIdentity
from crawler_control.models import StagingProduct
from offers.models import Offer


class BestsellerDemoCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_standard_categories", verbosity=0)

    def test_imports_all_standard_categories_through_staging_and_is_idempotent(self):
        call_command(
            "load_bestseller_demo",
            per_category=1,
            skip_images=True,
            verbosity=0,
        )

        documents = ProductSearchDocument.objects.filter(
            market__code="GB",
            is_searchable=True,
            spu__source_identities__source_system="joybuy",
            spu__source_identities__source_id__in=[
                "100647435",
                "10323362",
                "100004340049346",
                "100002040003455",
                "10376371",
                "10489713",
                "10447471",
                "100002485001401",
                "10010061",
                "100018940417708",
                "10534883",
            ],
        )
        self.assertEqual(documents.count(), 11)
        self.assertEqual(
            set(documents.values_list("local_category__slug", flat=True)),
            {
                "home-living",
                "electronics",
                "beauty-personal-care",
                "small-home-appliances",
                "health-wellness",
                "clothing-accessories",
                "computers-accessories",
                "outdoor-sports",
                "pet-supplies",
                "baby-toddler",
                "games-accessories",
            },
        )
        self.assertEqual(
            StagingProduct.objects.filter(
                parser_version="joybuy-bestseller-demo-1",
                status=StagingProduct.Status.IMPORTED,
            ).count(),
            11,
        )
        self.assertEqual(
            str(
                Offer.objects.get(
                    sku__source_identities__source_system="joybuy",
                    sku__source_identities__source_id="100647435",
                    market__code="GB",
                ).current_price
            ),
            "4.8200",
        )

        before = SpuSourceIdentity.objects.filter(source_system="joybuy").count()
        call_command(
            "load_bestseller_demo",
            per_category=1,
            skip_images=True,
            verbosity=0,
        )
        self.assertEqual(SpuSourceIdentity.objects.filter(source_system="joybuy").count(), before)
