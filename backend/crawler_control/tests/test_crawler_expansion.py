import sys
import unittest
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_control.models import CrawlJob  # noqa: E402
from crawler_control.services import create_crawl_job, mark_job_ready  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402

SCRAPY_AVAILABLE = find_spec("scrapy") is not None

FIXTURES_DIR = CRAWLER_DIR / "fixtures"


class ExpansionPlanTests(CrawlerControlTestBase):
    """Category expansion against the seeded joybuy fixture tree."""

    def test_current_only_vs_include_subcategories(self):
        current_only = create_crawl_job(
            name="Current only",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=10,
            include_subcategories=False,
        )
        with_children = create_crawl_job(
            name="With children",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=10,
            include_subcategories=True,
        )

        from joybuy_crawler.expansion import expand_job_categories

        only_scopes = expand_job_categories(current_only)
        child_scopes = expand_job_categories(with_children)

        self.assertEqual([scope.source_id for scope in only_scopes], ["l2-electronics"])
        self.assertEqual(
            [scope.source_id for scope in child_scopes],
            ["l2-electronics", "l3-phones"],
        )
        self.assertEqual(child_scopes[1].depth, 2)
        self.assertTrue(child_scopes[1].path.startswith(child_scopes[0].path))

    def test_expansion_uses_bound_tree_version(self):
        # Publish a newer tree where Electronics was renamed; the job stays
        # bound to the older snapshot for reproducibility.
        from catalog.services import save_source_category_version
        from django.utils import timezone
        from joybuy_crawler.expansion import expand_job_categories

        newer = save_source_category_version(
            source_system="joybuy",
            version_key="2026-11-08",
            captured_at=timezone.now(),
            nodes=[
                {"source_id": "l1-root", "name": "Root", "parent_source_id": None},
                {
                    "source_id": "l2-electronics",
                    "name": "Tech & Gadgets",
                    "parent_source_id": "l1-root",
                },
                {
                    "source_id": "l3-phones",
                    "name": "Smartphones",
                    "parent_source_id": "l2-electronics",
                },
            ],
        )
        newer.status = "PUBLISHED"
        newer.published_at = timezone.now()
        newer.save(update_fields=["status", "published_at"])

        unbound = create_crawl_job(
            name="Unbound job",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=5,
            include_subcategories=True,
        )
        bound = create_crawl_job(
            name="Bound job",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=5,
            include_subcategories=True,
            source_tree_version=self.version,
        )

        self.assertEqual(
            [scope.name for scope in expand_job_categories(unbound)],
            ["Tech & Gadgets", "Smartphones"],
        )
        self.assertEqual(
            [scope.name for scope in expand_job_categories(bound)],
            ["Electronics", "Phones"],
        )
        self.assertEqual(expand_job_categories(bound)[0].tree_version_key, "2026-11-02")

    def test_listing_targets_paginate_to_the_job_limit(self):
        from joybuy_crawler.expansion import build_crawl_plan

        job = mark_job_ready(
            create_crawl_job(
                name="Paginated",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=55,
                include_subcategories=False,
            )
        )
        plan = build_crawl_plan(job, base_url="https://fixture.test", per_page=30)
        self.assertEqual(len(plan.targets), 2)
        self.assertEqual(
            [target.page for target in plan.targets],
            [1, 2],
        )
        for target in plan.targets:
            self.assertTrue(
                target.url.startswith("https://fixture.test/l2-electronics?sort=default")
            )

        job_one_page = mark_job_ready(
            create_crawl_job(
                name="Single page",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                include_subcategories=False,
            )
        )
        plan_one = build_crawl_plan(job_one_page, base_url="https://fixture.test", per_page=30)
        self.assertEqual(len(plan_one.targets), 1)

    def test_sort_strategies_map_to_deterministic_urls_and_random_needs_seed(self):
        from joybuy_crawler.expansion import (
            build_listing_targets,
            expand_job_categories,
            order_targets,
        )

        scopes = expand_job_categories(
            create_crawl_job(
                name="Scopes",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
            )
        )
        targets = build_listing_targets(
            scopes,
            listing_sort=CrawlJob.ListingSort.BEST_SELLING,
            product_limit=10,
            base_url="https://fixture.test",
        )
        self.assertIn("sort=sales", targets[0].url)

        with self.assertRaises(ValueError):
            order_targets(targets, listing_sort=CrawlJob.ListingSort.RANDOM, random_seed=None)

    def test_random_order_is_reproducible_from_the_persisted_seed(self):
        from joybuy_crawler.expansion import build_crawl_plan

        seed = 42
        job_a = mark_job_ready(
            create_crawl_job(
                name="Random A",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                listing_sort=CrawlJob.ListingSort.RANDOM,
                include_subcategories=True,
            )
        )
        job_a.random_seed = seed
        job_a.save(update_fields=["random_seed"])
        job_b = mark_job_ready(
            create_crawl_job(
                name="Random B",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=10,
                listing_sort=CrawlJob.ListingSort.RANDOM,
                include_subcategories=True,
            )
        )
        job_b.random_seed = seed
        job_b.save(update_fields=["random_seed"])

        plan_a = build_crawl_plan(job_a, base_url="https://fixture.test", per_page=30)
        plan_b = build_crawl_plan(job_b, base_url="https://fixture.test", per_page=30)
        self.assertEqual(
            [target.url for target in plan_a.targets],
            [target.url for target in plan_b.targets],
            "The same seed must produce the same target order.",
        )
        # Shuffled, not just source order (4 targets from 2 scopes).
        self.assertNotEqual(
            [target.url for target in plan_a.targets][:2],
            [target.url for target in build_listing_source_order(plan_a)][:2],
        )


def build_listing_source_order(plan):
    return sorted(plan.targets, key=lambda target: (target.scope.source_id, target.page))


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class ListingParserAndDedupTests(unittest.TestCase):
    def test_listing_parser_contract_with_fixture(self):
        from joybuy_crawler.parsers.listing import (
            LISTING_STRUCTURE_VERSION,
            ListingStructureChanged,
            parse_listing_products,
        )

        self.assertEqual(LISTING_STRUCTURE_VERSION, 1)
        html = (FIXTURES_DIR / "listing_page_v1.html").read_text(encoding="utf-8")
        entries = parse_listing_products(html)
        self.assertEqual([entry.rank for entry in entries], [1, 2, 3, 4, 5, 6])
        self.assertEqual(entries[0].source_url, "/p/1001.html")
        self.assertEqual(entries[0].title, "Wireless Earbuds Pro")

        with self.assertRaises(ListingStructureChanged):
            parse_listing_products("<html><body><p>redesign</p></body></html>")

    def test_cross_category_product_urls_are_deduped(self):
        from joybuy_crawler.expansion import dedupe_product_urls
        from joybuy_crawler.parsers.listing import parse_listing_products

        electronics = parse_listing_products(
            (FIXTURES_DIR / "listing_page_v1.html").read_text(encoding="utf-8")
        )
        accessories = parse_listing_products(
            (FIXTURES_DIR / "listing_accessories_v1.html").read_text(encoding="utf-8")
        )

        combined = dedupe_product_urls([*electronics, *accessories])
        urls = [entry.source_url for entry in combined]
        self.assertEqual(len(urls), len(set(urls)))
        # 8 unique products (6 electronics + 3 accessories sharing /p/1003.html).
        self.assertEqual(len(combined), 8)
        # First-seen order and source ranks are preserved.
        self.assertEqual(urls[:3], ["/p/1001.html", "/p/1002.html", "/p/1003.html"])
        cable = next(entry for entry in combined if entry.source_url == "/p/1003.html")
        self.assertEqual(cable.rank, 3, "First-seen rank from Electronics is kept.")
