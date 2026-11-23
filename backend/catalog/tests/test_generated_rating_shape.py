"""生成评分脚本的纯函数与搜索文档回退测试（2026-11-23）。

脚本位于 ``var/gen_rating_20261123/generate.py``（不写库的纯函数部分），
这里用 importlib 按路径加载，避免把 var/ 变成 Python 包。
"""

import importlib.util
import random
import unittest
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from offers.models import Market
from reviews.services import upsert_source_review

from catalog.models import SpuDetail
from catalog.product_services import get_or_create_spu_from_source
from catalog.search_services import rebuild_search_document


def _load_generator():
    path = Path(settings.REPOSITORY_ROOT) / "var" / "gen_rating_20261123" / "generate.py"
    spec = importlib.util.spec_from_file_location("gen_rating_20261123_generate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load_generator()


class GeneratedRatingShapeTests(unittest.TestCase):
    def test_distribution_sums_to_count_and_is_staircase(self):
        rng = random.Random(20261123)
        for _ in range(500):
            count = rng.randint(50, 1500)
            distribution, _average = generator.generate_rating_distribution(rng, count)
            self.assertEqual(sum(distribution.values()), count)
            self.assertGreater(distribution["5"], distribution["4"])
            self.assertGreater(distribution["4"], distribution["3"])

    def test_average_stays_in_range(self):
        rng = random.Random(7)
        for _ in range(500):
            count = rng.randint(50, 1500)
            _distribution, average = generator.generate_rating_distribution(rng, count)
            self.assertGreaterEqual(average, Decimal("4.09"))
            self.assertLessEqual(average, Decimal("4.61"))

    def test_forced_minimum_stars_for_100_plus(self):
        rng = random.Random(11)
        for count in (100, 101, 149, 150, 500, 1000, 1500):
            for _ in range(20):
                distribution, _average = generator.generate_rating_distribution(rng, count)
                self.assertGreaterEqual(distribution["1"], 1)
                self.assertGreaterEqual(distribution["2"], 1)

    def test_share_bounds(self):
        rng = random.Random(3)
        for _ in range(300):
            count = rng.randint(50, 1500)
            distribution, _average = generator.generate_rating_distribution(rng, count)
            self.assertGreaterEqual(distribution["3"] / count, 0.08)
            self.assertLessEqual(distribution["3"] / count, 0.18)
            self.assertGreaterEqual(distribution["4"] / count, 0.22)
            self.assertLessEqual(distribution["4"] / count, 0.34)
            # 5 星为「余下」，需求给出约 45~65%。
            self.assertGreaterEqual(distribution["5"] / count, 0.45)
            self.assertLessEqual(distribution["5"] / count, 0.65)
            # 1 星在 N=100~124 时因「强制 >=1 条」可略超 0.8%。
            self.assertLessEqual(distribution["1"] / count, 0.008 + 1 / count)
            self.assertLessEqual(distribution["2"] / count, 0.02)

    def test_same_seed_is_deterministic(self):
        first = generator.generate_rating_distribution(random.Random(99), 888)
        second = generator.generate_rating_distribution(random.Random(99), 888)
        self.assertEqual(first, second)


class FormatSoldTests(unittest.TestCase):
    def test_below_1000_is_exact(self):
        self.assertEqual(generator.format_sold(0), "0")
        self.assertEqual(generator.format_sold(486), "486")
        self.assertEqual(generator.format_sold(999), "999")

    def test_1000_and_above_uses_k_plus(self):
        self.assertEqual(generator.format_sold(1000), "1k+")
        self.assertEqual(generator.format_sold(1200), "1.2k+")
        self.assertEqual(generator.format_sold(1500), "1.5k+")
        self.assertEqual(generator.format_sold(23000), "23k+")

    def test_parse_sold(self):
        self.assertEqual(generator.parse_sold(""), 0)
        self.assertEqual(generator.parse_sold(None), 0)
        self.assertEqual(generator.parse_sold("486"), 486)
        self.assertEqual(generator.parse_sold("10+"), 10)
        self.assertEqual(generator.parse_sold("1.2k+"), 1200)
        self.assertIsNone(generator.parse_sold("n/a"))


class SearchDocumentRatingFallbackTests(TestCase):
    def setUp(self):
        self.market = Market.objects.get(code="GB")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="rating-fallback-spu",
            title="Rating Fallback Product",
        )

    def test_falls_back_to_spu_detail_snapshot_without_local_reviews(self):
        SpuDetail.objects.create(
            spu=self.spu,
            rating_average=Decimal("4.50"),
            rating_count=9,
            rating_distribution={"5": 7, "4": 1, "1": 1},
        )
        document = rebuild_search_document(self.spu, market=self.market)
        self.assertEqual(document.rating_count, 9)
        self.assertEqual(document.rating_average, Decimal("4.50"))

    def test_local_reviews_win_over_spu_detail_snapshot(self):
        SpuDetail.objects.create(
            spu=self.spu,
            rating_average=Decimal("4.50"),
            rating_count=9,
            rating_distribution={"5": 7, "4": 1, "1": 1},
        )
        upsert_source_review(
            self.spu,
            source_system="joybuy",
            source_id="rating-fallback-review",
            rating=1,
            guest_display_name="Guest",
        )
        document = rebuild_search_document(self.spu, market=self.market)
        self.assertEqual(document.rating_count, 1)
        self.assertEqual(document.rating_average, Decimal("1.00"))
