"""Joybuy 菜单 → 本地二级类目同步命令的针对性测试（2026-11-09）。"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import (
    CategoryMapping,
    LocalCategory,
    SourceCategory,
    SourceCategoryTreeVersion,
)
from catalog.services import create_local_category, save_source_category_version


class SyncLocalCategoriesFromJoybuyTests(TestCase):
    def setUp(self):
        call_command("seed_standard_categories", stdout=StringIO())
        nodes = [
            {
                "source_id": "minihome:UK-Mini-HP-Home-Living",
                "name": "Home & Living",
                "name_zh": "家居生活",
                "parent_source_id": None,
            },
            {
                "source_id": "l2:1572",
                "name": "Kitchen & Dining",
                "name_zh": "厨房与餐厅用品",
                "parent_source_id": "minihome:UK-Mini-HP-Home-Living",
            },
            {
                "source_id": "l2:1564",
                "name": "Furniture",
                "name_zh": "家具",
                "parent_source_id": "minihome:UK-Mini-HP-Home-Living",
            },
            {
                "source_id": "l2:1580",
                "name": "Seasonal Decor",
                "name_zh": "节庆装饰品",
                "parent_source_id": "minihome:UK-Mini-HP-Home-Living",
            },
            {
                "source_id": "minihome:UK-Mini-HP-Automotive",
                "name": "Automotive",
                "name_zh": "汽车及零配件",
                "parent_source_id": None,
            },
            {
                "source_id": "l2:3900",
                "name": "Car Repair Tools",
                "name_zh": "汽车维修工具",
                "parent_source_id": "minihome:UK-Mini-HP-Automotive",
            },
        ]
        version = save_source_category_version(
            source_system="joybuy_uk",
            version_key="test-20261109",
            nodes=nodes,
            captured_at=timezone.now(),
        )
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])

        # 模拟历史同步曾把「节庆装饰品」建成普通二级：命令应清掉它，
        # 以后导入时按 Spu.is_activity 处理。
        home = LocalCategory.objects.get(slug="home-living")
        self.seasonal = create_local_category(
            name="节庆装饰品",
            slug="seasonal-decor",
            parent=home,
            sort_order=99,
        )
        self.seasonal_source = SourceCategory.objects.get(
            catalog__source_system="joybuy_uk", source_id="l2:1580"
        )
        CategoryMapping.objects.create(
            local_category=self.seasonal,
            source_category=self.seasonal_source,
            is_primary=True,
        )

    def _run(self, *args):
        output = StringIO()
        call_command("sync_local_categories_from_joybuy", *args, stdout=output)
        return output.getvalue()

    def test_merges_promotes_and_creates_children(self):
        home = LocalCategory.objects.get(slug="home-living")
        kitchen = LocalCategory.objects.get(slug="kitchen-essentials")
        # 模拟旧名称：命令应按 Joybuy 名称改名，但保留原 slug。
        kitchen.name_zh = "旧厨房名"
        kitchen.save(update_fields=["name_zh", "updated_at"])

        self._run()

        kitchen.refresh_from_db()
        self.assertEqual(kitchen.name_zh, "厨房与餐厅用品")
        self.assertEqual(kitchen.name_en, "Kitchen & Dining")
        furniture = LocalCategory.objects.get(slug="furniture")
        self.assertEqual(furniture.parent_id, home.pk)
        self.assertEqual(furniture.name_zh, "家具")
        # 多对一映射：Joybuy 二级 → 本地二级；频道 → 本地一级。
        self.assertTrue(
            CategoryMapping.objects.filter(
                source_category__source_id="l2:1572",
                local_category=kitchen,
                is_primary=True,
            ).exists()
        )
        self.assertTrue(
            CategoryMapping.objects.filter(
                source_category__source_id="minihome:UK-Mini-HP-Home-Living",
                local_category=home,
            ).exists()
        )
        # 汽车类明确未映射：不创建本地二级。
        self.assertFalse(LocalCategory.objects.filter(slug="car-repair-tools").exists())
        self.assertFalse(
            CategoryMapping.objects.filter(source_category__source_id="l2:3900").exists()
        )
        # 节庆装饰品不再建本地二级：旧 seasonal-decor 与映射都被清理。
        self.assertFalse(LocalCategory.objects.filter(slug="seasonal-decor").exists())
        self.assertFalse(
            CategoryMapping.objects.filter(source_category__source_id="l2:1580").exists()
        )

    def test_dry_run_writes_nothing(self):
        output = self._run("--dry-run")
        self.assertIn("新建 1", output)
        self.assertIn("活动商品节点 1", output)
        self.assertIn("清理退役/活动类目 1", output)
        self.assertFalse(LocalCategory.objects.filter(slug="furniture").exists())
        self.assertFalse(
            CategoryMapping.objects.filter(source_category__source_id="l2:1564").exists()
        )
        self.assertTrue(LocalCategory.objects.filter(slug="seasonal-decor").exists())

    def test_rerun_is_idempotent(self):
        self._run()
        count = LocalCategory.objects.count()
        output = self._run()
        self.assertIn("新建 0", output)
        self.assertEqual(LocalCategory.objects.count(), count)


class RetiredBucketPruneTests(TestCase):
    """一对一拆分（2026-11-11）：旧桶 slug 无引用时退役、有商品时保留。"""

    def _seed_and_sync(self):
        from io import StringIO

        call_command("seed_standard_categories", stdout=StringIO())
        nodes = [
            {
                "source_id": "minihome:UK-Mini-HP-Home-Living",
                "name": "Home & Living",
                "name_zh": "家居生活",
                "parent_source_id": None,
            },
            {
                "source_id": "l2:1564",
                "name": "Furniture",
                "name_zh": "家具",
                "parent_source_id": "minihome:UK-Mini-HP-Home-Living",
            },
        ]
        version = save_source_category_version(
            source_system="joybuy_uk",
            version_key="test-retired-20261111",
            nodes=nodes,
            captured_at=timezone.now(),
        )
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])

    def test_empty_retired_bucket_is_removed(self):
        self._seed_and_sync()
        home = LocalCategory.objects.get(slug="home-living")
        LocalCategory.objects.create(
            name="食品杂货",
            slug="groceries-food",
            parent=home,
            depth=1,
            path=f"/{home.pk}/groceries-food/",
        )
        output = StringIO()
        call_command("sync_local_categories_from_joybuy", stdout=output)
        self.assertFalse(LocalCategory.objects.filter(slug="groceries-food").exists())
        self.assertIn("清理退役/活动类目 1", output.getvalue())

    def test_retired_bucket_with_spu_is_kept(self):
        from catalog.models import Spu

        self._seed_and_sync()
        home = LocalCategory.objects.get(slug="home-living")
        bucket = LocalCategory.objects.create(
            name="食品杂货",
            slug="groceries-food",
            parent=home,
            depth=1,
            path=f"/{home.pk}/groceries-food/",
        )
        Spu.objects.create(local_category=bucket, is_activity=False)
        output = StringIO()
        call_command("sync_local_categories_from_joybuy", stdout=output)
        self.assertTrue(LocalCategory.objects.filter(slug="groceries-food").exists())
        self.assertIn("保留待迁移类目 groceries-food：有商品", output.getvalue())


class DeepNodeRetirementTests(TestCase):
    """Joybuy 深层节点（下拉里不出现）不再当成本地二级（2026-11-11 全频道对齐）。

    旧抓取把 ``l3:*`` 深层节点也当二级抓下来，于是出现过「显示器 / 游戏显示器」
    这类跨频道同名二级。现在以现网分类下拉为准：这些深层节点不建本地类目，
    同名消歧问题随之消失。
    """

    def _sync_tree(self, nodes, version_key="test-deep-20261111"):
        version = save_source_category_version(
            source_system="joybuy_uk",
            version_key=version_key,
            nodes=nodes,
            captured_at=timezone.now(),
        )
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])
        output = StringIO()
        call_command("sync_local_categories_from_joybuy", stdout=output)
        return output.getvalue()

    def test_deep_nodes_are_not_created_as_local_categories(self):
        from io import StringIO

        call_command("seed_standard_categories", stdout=StringIO())
        electronics_ch = "minihome:UK-Mini-HP-Electronics"
        gaming_ch = "minihome:UK-Mini-HP-Gaming"
        nodes = [
            {
                "source_id": electronics_ch,
                "name": "Electronics",
                "name_zh": "电子产品",
                "parent_source_id": None,
                "sort_order": 0,
            },
            {
                "source_id": gaming_ch,
                "name": "Gaming",
                "name_zh": "游戏",
                "parent_source_id": None,
                "sort_order": 1,
            },
            {
                "source_id": "l2:1436",
                "name": "Monitors",
                "name_zh": "显示器",
                "parent_source_id": electronics_ch,
                "sort_order": 0,
            },
            {
                # 深层节点：下拉里不出现 → 不建本地二级
                "source_id": "l3:1437",
                "name": "Gaming Monitors",
                "name_zh": "游戏显示器",
                "parent_source_id": gaming_ch,
                "sort_order": 0,
            },
        ]
        self._sync_tree(nodes)
        monitors = LocalCategory.objects.get(slug="monitors")
        self.assertEqual(monitors.parent.slug, "computers-accessories")
        self.assertFalse(LocalCategory.objects.filter(slug="gaming-monitors").exists())
        self.assertFalse(
            CategoryMapping.objects.filter(source_category__source_id="l3:1437").exists()
        )
        self.assertTrue(
            CategoryMapping.objects.filter(
                source_category__source_id="l2:1436", local_category=monitors, is_primary=True
            ).exists()
        )


class PetsOneToOneTests(TestCase):
    """宠物用品 13 个二级与 Joybuy 现网一对一（2026-11-11 补齐 5 个新节点）。"""

    PETS_CH = "minihome:UK-Mini-HP-Pets"
    # 现网菜单顺序（2026-11-11 实测）：13 个二级，含 5 个新增节点。
    LIVE = [
        ("l2:1363", "Cat Food", "猫粮"),
        ("l2:4707", "Cat Litter", "猫砂"),
        ("l2:1364", "Dog Food", "狗粮"),
        ("l2:3532", "Cat Treats", "猫零食"),
        ("l2:5441", "Dog Treats", "狗零食"),
        ("l2:4711", "Smart Pet Appliances", "智能宠物电器"),
        ("l2:4713", "Dog Toys", "狗玩具"),
        ("l2:3540", "Cat Toys", "猫玩具"),
        ("l2:1365", "Small Animals", "小宠用品"),
        ("l2:3534", "Other Animals", "其他动物用品"),
        ("l2:3542", "Pet Supplies & Accesories", "宠物用品与配件"),
        ("l2:3536", "Healthcare & Wellness", "医疗保健与营养"),
        ("l2:3538", "Pet Grooming", "宠物美容护理"),
    ]

    def _sync(self):
        from io import StringIO

        call_command("seed_standard_categories", stdout=StringIO())
        nodes = [
            {
                "source_id": self.PETS_CH,
                "name": "Pets",
                "name_zh": "宠物用品",
                "parent_source_id": None,
            }
        ] + [
            {
                "source_id": sid,
                "name": en,
                "name_zh": zh,
                "parent_source_id": self.PETS_CH,
                "sort_order": index,
            }
            for index, (sid, en, zh) in enumerate(self.LIVE)
        ]
        version = save_source_category_version(
            source_system="joybuy_uk",
            version_key="test-pets-20261111",
            nodes=nodes,
            captured_at=timezone.now(),
        )
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])
        call_command("sync_local_categories_from_joybuy", stdout=StringIO())

    def test_thirteen_children_match_live_menu_in_order(self):
        self._sync()
        pets = LocalCategory.objects.get(slug="pet-supplies")
        children = list(
            LocalCategory.objects.filter(parent=pets).order_by("sort_order", "id")
        )
        self.assertEqual(len(children), 13)
        self.assertEqual([c.name_zh for c in children], [zh for _, _, zh in self.LIVE])
        # 每个现网节点各自一对一映射到自己的本地二级。
        for sid, _en, _zh in self.LIVE:
            mapping = CategoryMapping.objects.get(
                source_category__source_id=sid, is_primary=True
            )
            self.assertEqual(mapping.local_category.parent_id, pets.pk)

    def test_new_pet_slugs_are_stable(self):
        self._sync()
        for slug in (
            "cat-litter",
            "dog-treats",
            "smart-pet-appliances",
            "dog-toys",
            "small-animals",
        ):
            self.assertTrue(
                LocalCategory.objects.filter(slug=slug, parent__slug="pet-supplies").exists(),
                slug,
            )
