from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import (
    CategoryMapping,
    LocalCategory,
    ProductSearchDocument,
    SourceCatalog,
    SourceCategory,
    Spu,
)
from catalog.product_services import get_or_create_spu_from_source
from offers.models import Market

STANDARD_ROOT_SLUGS = [
    "home-living",
    "electronics",
    "beauty-personal-care",
    "small-home-appliances",
    "health-wellness",
    "computers-accessories",
    "clothing-accessories",
    "outdoor-sports",
    "pet-supplies",
    "baby-toddler",
    "games-accessories",
]


class SeedStandardCategoriesTests(TestCase):
    def call_seed(self, *args):
        out = StringIO()
        call_command("seed_standard_categories", *args, stdout=out)
        return out.getvalue()

    def test_creates_eleven_bilingual_roots_in_order(self):
        self.call_seed()
        roots = list(
            LocalCategory.objects.filter(
                parent__isnull=True, status=LocalCategory.Status.ACTIVE
            ).order_by("sort_order")
        )
        self.assertEqual([root.slug for root in roots], STANDARD_ROOT_SLUGS)
        home = roots[0]
        self.assertEqual(home.name_en, "Home & Living")
        self.assertEqual(home.name_zh, "家居生活")
        self.assertEqual(
            list(home.children.values_list("slug", flat=True)),
            [
                "kitchen-essentials",
                "home-storage",
                "bedding-textiles",
                "cleaning-supplies",
                "rice-pasta-pulses",
            ],
        )
        self.assertEqual(home.children.first().name_zh, "厨房与餐厅用品")

    def test_seed_does_not_resurrect_retired_bucket_children(self):
        """2026-11-11 一对一类目拆分：退役桶/基座二级不得被 seed 复活。"""

        RETIRED = [
            "groceries-food",
            "phones-tablets",
            "laptops-desktops",
            "pc-components",
            "tv-audio",
            "pet-food",
            "pet-toys",
            "toys-early-learning",
            "networking",
            "cycling",
            "water-sports",
            "personal-care-appliances",
            "gaming-accessories",
            "board-card-games",
        ]
        self.call_seed()
        self.assertFalse(LocalCategory.objects.filter(slug__in=RETIRED).exists())

    def test_hides_legacy_roots_outside_the_standard_list(self):
        LocalCategory.objects.create(name="Legacy", slug="legacy-root", depth=0, path="/x/")
        self.call_seed()
        legacy = LocalCategory.objects.get(slug="legacy-root")
        self.assertEqual(legacy.status, LocalCategory.Status.HIDDEN)

    def test_rerun_is_idempotent(self):
        self.call_seed()
        self.call_seed()
        self.assertEqual(
            LocalCategory.objects.filter(parent__isnull=True).count(), len(STANDARD_ROOT_SLUGS)
        )

    def test_assign_demo_products_maps_titles_and_rebuilds_documents(self):
        market = Market.objects.get(code="GB")
        air_fryer, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="demo-airfryer",
            title="Tristar Multi Crispy Air Fryer Oven - 10L",
        )
        ramen, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="demo-ramen",
            title="Samyang Buldak Hot Chicken Ramen",
        )
        self.call_seed("--assign-demo-products")
        air_fryer.refresh_from_db()
        ramen.refresh_from_db()
        self.assertEqual(air_fryer.local_category.slug, "kitchen-appliances")
        self.assertEqual(ramen.local_category.slug, "rice-pasta-pulses")
        self.assertTrue(
            ProductSearchDocument.objects.filter(
                spu=air_fryer, market=market, local_category=air_fryer.local_category
            ).exists()
        )
        self.assertTrue(Spu.objects.filter(pk=ramen.pk, local_category=ramen.local_category).exists())


class CategoryTreeApiTests(TestCase):
    def test_category_tree_returns_bilingual_roots_with_children(self):
        call_command("seed_standard_categories")
        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        roots = payload["categories"]
        self.assertEqual([root["slug"] for root in roots], STANDARD_ROOT_SLUGS)
        home = roots[0]
        self.assertEqual(home["name_en"], "Home & Living")
        self.assertEqual(home["name_zh"], "家居生活")
        self.assertTrue(home["children"])
        self.assertIn("name_zh", home["children"][0])
        self.assertEqual(home["children"][0]["slug"], "kitchen-essentials")

    @staticmethod
    def _create_channel_source(source_id: str) -> SourceCategory:
        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system="joybuy",
            defaults={"display_name": "Joybuy UK"},
        )
        now = timezone.now()
        return SourceCategory.objects.create(
            catalog=catalog,
            source_id=source_id,
            first_seen_at=now,
            last_seen_at=now,
        )

    def test_category_tree_exposes_channel_code_on_depth_zero_rows(self):
        """频道落地页入口：depth=0 行带 channel_code，二级行不带。"""

        call_command("seed_standard_categories")
        home = LocalCategory.objects.get(slug="home-living", parent__isnull=True)
        # 家居生活挂了两个频道：按 casefold 排序取 Home-Living（< Joymart）。
        for source_id in ["minihome:UK-Mini-HP-Joymart", "minihome:UK-Mini-HP-Home-Living"]:
            CategoryMapping.objects.create(
                local_category=home,
                source_category=self._create_channel_source(source_id),
                is_primary=True,
            )
        response = self.client.get(reverse("category-tree"))
        self.assertEqual(response.status_code, 200)
        roots = {root["slug"]: root for root in response.json()["categories"]}
        self.assertEqual(roots["home-living"]["channel_code"], "UK-Mini-HP-Home-Living")
        # 没有 minihome: 映射的一级返回 None（前端降级 /c/<slug>）。
        self.assertIsNone(roots["computers-accessories"]["channel_code"])
        # 二级行没有 channel_code 字段。
        self.assertNotIn("channel_code", roots["home-living"]["children"][0])
