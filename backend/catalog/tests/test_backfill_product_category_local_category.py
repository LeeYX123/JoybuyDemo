"""``backfill_product_category_local_category`` 的针对性测试（2026-11-23 批次 A）。

覆盖：DRY_RUN 只读；``--apply`` 按映射写入并导出备份/清单；重跑幂等；
已有不同映射的人工值不被覆盖；``joybuy`` 下的孤儿行不在范围内。
"""

import csv
import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from catalog.models import LocalCategory, ProductCategory, SourceCatalog

COMMAND = "backfill_product_category_local_category"


class BackfillProductCategoryLocalCategoryTests(TestCase):
    def setUp(self):
        self.catalog = SourceCatalog.objects.create(
            source_system="joybuy_uk", display_name="Joybuy UK"
        )
        self.other_catalog = SourceCatalog.objects.create(
            source_system="joybuy", display_name="Joybuy"
        )
        self.local = {}
        for slug, depth, path in (
            ("electronics", 0, "/electronics/"),
            ("home-living", 0, "/home-living/"),
            ("beauty-personal-care", 0, "/beauty-personal-care/"),
        ):
            self.local[slug] = LocalCategory.objects.create(
                name=slug, slug=slug, depth=depth, path=path
            )
        self.local["electronics-accessories"] = LocalCategory.objects.create(
            name="电子配件",
            slug="electronics-accessories",
            depth=1,
            path="/electronics/electronics-accessories/",
            parent=self.local["electronics"],
        )
        # 计划里 1849/1801（电子产品 > 配件）、1171/16307（生鲜 > 肉禽）、
        # 4（美妆根）；16377 属 34 条待确认，不写。
        self.electronics = self._product_category("1849", "Electronics", 0, "/1849/")
        self.accessories = self._product_category(
            "1801", "Accessories", 1, "/1849/1801/", parent=self.electronics
        )
        self.fresh = self._product_category("1171", "Fresh & Chilled Food", 0, "/1171/")
        self.meat = self._product_category("16307", "Meat & Fish", 1, "/1171/16307/", self.fresh)
        self.vegetarian = self._product_category(
            "16377", "Vegetarian & Vegan", 1, "/1171/16377/", self.fresh
        )
        self.beauty = self._product_category("4", "Beauty", 0, "/4/")
        # catalog=joybuy 的孤儿行（同 source_id，无商品）：不应被写。
        self.orphan = ProductCategory.objects.create(
            catalog=self.other_catalog,
            source_id="4909",
            name="Seasonal & Party",
            depth=0,
            path="/4909/",
        )

    def _product_category(self, source_id, name, depth, path, parent=None):
        return ProductCategory.objects.create(
            catalog=self.catalog,
            source_id=source_id,
            name=name,
            depth=depth,
            path=path,
            parent=parent,
        )

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            call_command(COMMAND, "--output-dir", tmp, stdout=io.StringIO())

            self.assertEqual(ProductCategory.objects.exclude(local_category=None).count(), 0)
            # DRY_RUN 也产出待确认清单，但不写备份。
            review = Path(tmp) / "review_needed.csv"
            self.assertTrue(review.exists())
            self.assertFalse((Path(tmp) / "backup_pc_mapping.json").exists())

    def test_apply_fills_planned_rows_and_writes_review_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            call_command(COMMAND, "--apply", "--output-dir", tmp, stdout=io.StringIO())

            self.accessories.refresh_from_db()
            self.meat.refresh_from_db()
            self.beauty.refresh_from_db()
            self.vegetarian.refresh_from_db()
            self.orphan.refresh_from_db()

            self.assertEqual(self.accessories.local_category.slug, "electronics-accessories")
            self.assertEqual(self.meat.local_category.slug, "home-living")
            self.assertEqual(self.beauty.local_category.slug, "beauty-personal-care")
            # 34 条待确认清单里的行保持未填。
            self.assertIsNone(self.vegetarian.local_category_id)
            self.assertIsNone(self.orphan.local_category_id)

            backup = json.loads((Path(tmp) / "backup_pc_mapping.json").read_text("utf-8"))
            self.assertEqual(backup["catalog"], "joybuy_uk")
            self.assertEqual(
                {row["source_id"] for row in backup["rows"]},
                {"1849", "1801", "1171", "16307", "16377", "4"},
            )
            self.assertTrue(
                all(row["local_category_slug_before"] is None for row in backup["rows"])
            )

            with (Path(tmp) / "review_needed.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["source_id"] for row in rows], ["16377"])
            self.assertEqual(rows[0]["suggested_local_slug"], "frozen-vegetarian-vegan")

    def test_reapply_is_idempotent_and_keeps_manual_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            call_command(COMMAND, "--apply", "--output-dir", tmp, stdout=io.StringIO())
            # 人工把 1801 改到美妆根：重跑必须保留，不覆盖。
            ProductCategory.objects.filter(pk=self.accessories.pk).update(
                local_category=self.local["beauty-personal-care"]
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            call_command(COMMAND, "--apply", "--output-dir", tmp, stdout=out)

        self.accessories.refresh_from_db()
        self.meat.refresh_from_db()
        self.assertEqual(self.accessories.local_category.slug, "beauty-personal-care")
        self.assertEqual(self.meat.local_category.slug, "home-living")
        self.assertIn("conflict=1", out.getvalue())
        self.assertIn("unchanged=4", out.getvalue())
