"""Tests for the 2026-11-05 crawler rebuild: tree sync, multi-category jobs,
unauthenticated runs, UK parsers, dataset writer and the staging pipeline."""

import json
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest import mock

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.test import TestCase  # noqa: E402

from crawler_control.models import (  # noqa: E402
    CrawlRun,
    CrawlRunEvent,
    StagingProduct,
)
from crawler_control.services import (  # noqa: E402
    create_crawl_job,
    mark_job_ready,
    start_run,
)
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)

SCRAPY_AVAILABLE = find_spec("scrapy") is not None


class TreeSyncTests(CrawlerControlTestBase):
    def _catalog(self):
        from catalog.models import SourceCatalog

        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system="joybuy_uk", defaults={"display_name": "Joybuy UK"}
        )
        return catalog

    def test_sync_publishes_version_with_verbatim_ids(self):
        from catalog.models import SourceCategorySnapshot
        from crawler_control.tree_sync import MenuNode, sync_category_tree, tree_to_payload

        catalog = self._catalog()
        nodes = [
            MenuNode(
                name="Electronics",
                source_id="l1:1409",
                source_url="https://www.joybuy.co.uk/s?k=Electronics&l1=1409",
                children=[
                    MenuNode(
                        name="Camera & Photo",
                        source_id="cid2:1416",
                        source_url="https://www.joybuy.co.uk/s?k=Camera&cid2=1416",
                    )
                ],
            )
        ]
        result = sync_category_tree(catalog, nodes, publish=True)

        self.assertEqual(result.tree_version.status, "PUBLISHED")
        self.assertEqual(result.tree_version.version_key, result.tree_version.version_key)
        self.assertTrue(result.tree_version.version_key.startswith("joybuy-uk-"))
        self.assertEqual(result.created_snapshots, 2)
        self.assertIn("l1:1409", result.new_source_ids)

        # Verbatim ids become real SourceCategory rows.
        category = SourceCategorySnapshot.objects.get(
            tree_version=result.tree_version, depth=0
        ).category
        self.assertEqual(category.source_id, "l1:1409")

        payload = tree_to_payload(result.tree_version)
        self.assertEqual(payload["version_key"], result.tree_version.version_key)
        self.assertEqual(len(payload["categories"]), 1)
        self.assertEqual(payload["categories"][0]["children"][0]["source_id"], "cid2:1416")

    def test_prune_food_nodes_hides_food_pickers(self):
        """2026-11-25 食品撤出商城：选择器 payload 剔除食品节点与整棵食品频道。"""
        from crawler_control.tree_sync import (
            MenuNode,
            latest_published_tree,
            prune_food_nodes,
            sync_category_tree,
            tree_to_payload,
        )

        catalog = self._catalog()
        sync_category_tree(
            catalog,
            [
                # Joymart：全部子节点都是食品 → 整棵频道隐藏
                MenuNode(
                    "Joymart",
                    "minihome:UK-Mini-HP-Joymart",
                    children=[MenuNode("Chocolate & Sweets", "l2:1277")],
                ),
                # 家居生活：食品子节点剔除，非食品保留
                MenuNode(
                    "Home & Living",
                    "minihome:UK-Mini-HP-Home-Living",
                    children=[
                        MenuNode("Wine", "l2:1329"),
                        MenuNode("Kitchen & Dining", "l2:1572"),
                    ],
                ),
                # 本来就没有子节点的频道：保留
                MenuNode("Bare Channel", "minihome:UK-Mini-HP-Bare"),
            ],
            publish=True,
        )
        latest = latest_published_tree(catalog)
        payload = prune_food_nodes(tree_to_payload(latest))

        sources = [root["source_id"] for root in payload["categories"]]
        self.assertNotIn("minihome:UK-Mini-HP-Joymart", sources)
        self.assertIn("minihome:UK-Mini-HP-Home-Living", sources)
        self.assertIn("minihome:UK-Mini-HP-Bare", sources)
        living = next(
            root
            for root in payload["categories"]
            if root["source_id"] == "minihome:UK-Mini-HP-Home-Living"
        )
        child_ids = [child["source_id"] for child in living["children"]]
        self.assertNotIn("l2:1329", child_ids)
        self.assertIn("l2:1572", child_ids)
        # 冻结版本本身不被改动：原始 payload 仍含食品节点
        raw = tree_to_payload(latest)
        self.assertIn(
            "l2:1329",
            [
                child["source_id"]
                for root in raw["categories"]
                for child in root.get("children", [])
            ],
        )

    def test_sync_reports_removed_ids_against_previous_version(self):
        from crawler_control.tree_sync import MenuNode, sync_category_tree

        catalog = self._catalog()
        first = sync_category_tree(
            catalog,
            [MenuNode("Electronics", "l1:1409"), MenuNode("Gaming", "l1:1407")],
            publish=True,
        )
        second = sync_category_tree(catalog, [MenuNode("Electronics", "l1:1409")], publish=True)

        self.assertNotEqual(first.tree_version.version_key, second.tree_version.version_key)
        self.assertEqual(second.missing_source_ids, ["l1:1407"])

    def test_sync_rejects_empty_or_unidentified_menu(self):
        from crawler_control.domain import CrawlJobParamsInvalid
        from crawler_control.tree_sync import MenuNode, sync_category_tree

        catalog = self._catalog()
        with self.assertRaises(CrawlJobParamsInvalid):
            sync_category_tree(catalog, [], publish=True)
        with self.assertRaises(CrawlJobParamsInvalid):
            sync_category_tree(catalog, [MenuNode("No id", "")], publish=True)

    def test_chinese_names_match_by_source_id_and_survive_resync(self):
        from crawler_control.tree_sync import (
            MenuNode,
            apply_chinese_names,
            sync_category_tree,
            tree_to_payload,
        )

        catalog = self._catalog()
        english = [
            MenuNode(
                name="Electronics",
                source_id="minihome:UK-Mini-HP-Electronics",
                children=[MenuNode(name="Phones", source_id="l2:1420")],
            )
        ]
        first = sync_category_tree(catalog, english, publish=True)

        result = apply_chinese_names(
            catalog,
            [
                MenuNode(
                    name="电子产品",
                    source_id="minihome:UK-Mini-HP-Electronics",
                    name_zh="电子产品",
                    children=[MenuNode(name="手机", source_id="l2:1420", name_zh="手机")],
                )
            ],
        )

        self.assertEqual(len(result.matched_source_ids), 2)
        self.assertEqual(result.unknown_source_ids, [])
        self.assertEqual(result.missing_source_ids, [])
        self.assertEqual(result.updated_categories, 2)
        self.assertEqual(result.updated_snapshots, 2)

        payload = tree_to_payload(first.tree_version)
        self.assertEqual(payload["categories"][0]["name"], "Electronics")
        self.assertEqual(payload["categories"][0]["name_zh"], "电子产品")
        self.assertEqual(payload["categories"][0]["children"][0]["name_zh"], "手机")

        # 英文名仍然是结构基线；重建一个新版本时中文名从 SourceCategory 继承。
        english.append(MenuNode(name="Pets", source_id="minihome:UK-Mini-HP-Pets"))
        second = sync_category_tree(catalog, english, publish=True)
        self.assertNotEqual(first.tree_version.version_key, second.tree_version.version_key)
        rebuilt = tree_to_payload(second.tree_version)
        electronics = next(
            node
            for node in rebuilt["categories"]
            if node["source_id"] == "minihome:UK-Mini-HP-Electronics"
        )
        self.assertEqual(electronics["name_zh"], "电子产品")

    def test_chinese_name_sync_reports_unknown_and_missing_ids(self):
        from crawler_control.tree_sync import (
            MenuNode,
            apply_chinese_names,
            sync_category_tree,
        )

        catalog = self._catalog()
        sync_category_tree(
            catalog,
            [
                MenuNode(
                    name="Electronics",
                    source_id="minihome:UK-Mini-HP-Electronics",
                    children=[MenuNode(name="Phones", source_id="l2:1420")],
                )
            ],
            publish=True,
        )

        result = apply_chinese_names(
            catalog,
            [
                MenuNode(
                    name="电子产品",
                    source_id="minihome:UK-Mini-HP-Electronics",
                    name_zh="电子产品",
                    children=[MenuNode(name="不存在", source_id="l2:9999", name_zh="不存在")],
                )
            ],
        )

        self.assertEqual(result.unknown_source_ids, ["l2:9999"])
        self.assertEqual(result.missing_source_ids, ["l2:1420"])
        self.assertEqual(result.matched_source_ids, ["minihome:UK-Mini-HP-Electronics"])


class MultiCategoryJobTests(CrawlerControlTestBase):
    def test_multi_category_selections_are_frozen_and_ordered(self):
        job = create_crawl_job(
            name="Multi job",
            market=self.market,
            source_catalog=self.catalog,
            source_categories=[
                {"category": self.l2, "include_descendants": True},
                {"category": self.l3, "include_descendants": False},
            ],
            product_limit=10,
        )
        selections = list(job.source_selections.order_by("sort_order"))
        self.assertEqual(len(selections), 2)
        self.assertEqual(selections[0].source_category_id, self.l2.pk)
        self.assertTrue(selections[0].include_descendants)
        self.assertFalse(selections[1].include_descendants)
        # Legacy column keeps the first selection; tree version is frozen.
        self.assertEqual(job.source_category_id, self.l2.pk)
        self.assertEqual(job.source_tree_version_id, self.version.pk)

        run = start_run(mark_job_ready(job))
        self.assertEqual(len(run.params_snapshot["source_categories"]), 2)
        self.assertEqual(
            run.params_snapshot["source_categories"][0]["source_category_id"], "l2-electronics"
        )

    def test_duplicate_selection_is_rejected(self):
        from crawler_control.domain import CrawlJobParamsInvalid

        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Dup job",
                market=self.market,
                source_catalog=self.catalog,
                source_categories=[
                    {"category": self.l2},
                    {"category": self.l2},
                ],
                product_limit=10,
            )

    def test_legacy_single_category_still_creates_one_selection(self):
        job = create_crawl_job(
            name="Legacy job",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=5,
        )
        self.assertEqual(job.source_selections.count(), 1)
        self.assertTrue(job.source_selections.first().include_descendants)

    def test_start_run_without_account_is_unauthenticated(self):
        job = mark_job_ready(
            create_crawl_job(
                name="No account job",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=5,
                account_group="empty-group",
            )
        )
        run = start_run(job)
        self.assertIsNone(run.account)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="RUN_UNAUTHENTICATED").exists())


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class JoybuyUkParserTests(unittest.TestCase):
    LISTING_HTML = """
    <div class="list">
      <a href="/dp/some-slug/104001"><span class="title">Kettle 1.7L</span>
        <span class="price"><span class="crossOffPrice">£29.99</span>
        <span class="mainPrice">£19.99</span></span>
        <img src="//images3.joy-sourcing.com/product/s480x480_p/k1.png.webp"/></a>
      <a href="/dp/other/104002"><span class="title">Toaster</span></a>
      <a href="/dp/some-slug/104001"><span>dup</span></a>
    </div>
    """

    def test_listing_parses_cards_with_original_price(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        entries = parse_uk_listing(self.LISTING_HTML)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].source_url, "https://www.joybuy.co.uk/dp/some-slug/104001")
        self.assertEqual(entries[0].original_price, "29.99")
        self.assertEqual(entries[0].rank, 1)
        self.assertTrue(entries[0].image_url.startswith("https://images3."))

    def test_listing_without_cards_raises(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        with self.assertRaises(RuntimeError):
            parse_uk_listing("<div>nothing here</div>")

    def test_detail_maps_joybuy_native_fields(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = """
        <html><body>
          <h1>Stainless Kettle 1.7L</h1>
          <span class="brand">Ochama</span>
          <span class="crossOffPrice">£29.99</span><span class="mainPrice">£19.99</span>
          <img src="https://images4.joy-sourcing.com/product/s480x480_p/k1.png.webp"/>
          <a href="/store/xiablaqa">xiablaqa</a>
          <div class="description">Fast boil kettle for tea.</div>
        </body></html>
        """
        product = parse_uk_product_detail(
            html, source_url="https://www.joybuy.co.uk/dp/kettle/104001"
        )
        self.assertEqual(product.source_id, "104001")
        self.assertEqual(product.title, "Stainless Kettle 1.7L")
        self.assertEqual(product.current_price, "29.99")
        self.assertIsNone(product.list_price)  # discount never kept
        self.assertEqual(product.main_price, "19.99")
        self.assertEqual(product.currency, "GBP")
        self.assertEqual(len(product.skus), 1)
        self.assertEqual(product.skus[0]["source_id"], "104001")
        payload = product.to_payload()
        # Joybuy-native block keeps source field names verbatim.
        self.assertEqual(payload["joybuy"]["productId"], "104001")
        self.assertEqual(payload["joybuy"]["priceInfo"]["crossOffPrice"], "29.99")
        self.assertEqual(payload["joybuy"]["priceInfo"]["mainPrice"], "19.99")
        self.assertEqual(payload["joybuy"]["skus"][0]["skuId"], "104001")
        self.assertEqual(payload["current_price"], "29.99")

    def test_image_variant_ladder_prefers_largest(self):
        from joybuy_crawler.image_variants import candidate_variants, resolve_highest_resolution

        url = "https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp"
        candidates = candidate_variants(url)
        # Ladder head is s1248 (live-verified hi-res variant, 2026-11-05).
        self.assertEqual(candidates[0], url.replace("s480x480", "s1248x1248"))
        self.assertIn(url, candidates)
        self.assertEqual(
            candidates[-1],
            "https://images3.joy-sourcing.com/product/p/k1.png.webp",
        )

        calls = []

        def fake_fetch(candidate, headers=None, timeout_seconds=30):
            calls.append(candidate)
            if "s1248x1248" in candidate:
                raise RuntimeError("404")

            class Result:
                status_code = 200
                body = b"image-bytes"

            return Result()

        with mock.patch("joybuy_crawler.image_variants.fetch_url", side_effect=fake_fetch):
            resolved_url, payload = resolve_highest_resolution(url)
        # s1248 fails, so the ladder lands on the next available size.
        self.assertEqual(resolved_url, url.replace("s480x480", "s800x800"))
        self.assertEqual(payload, b"image-bytes")
        self.assertEqual(calls[0], url.replace("s480x480", "s1248x1248"))


class DatasetTests(TestCase):
    """Dataset writer: per-category folders with a 1:1 index mapping."""

    def test_save_product_writes_json_images_and_index(self):
        from joybuy_crawler.dataset import save_product

        payload = {
            "source_id": "104001",
            "title": "Kettle",
            "image_urls": [
                "https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp",
                "https://images3.joy-sourcing.com/product/s480x480_p/k2.jpg!q70.webp",
            ],
            "detail_image_urls": [
                "https://images3.joy-sourcing.com/product/s480x480_d/d1.png.webp"
            ],
            "joybuy": {"breadcrumbs": [{"name": "Electronics"}, {"name": "Camera"}]},
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "job-a"

            def fake_resolve(url, timeout=30):
                return url, b"img:" + url.encode()

            index = save_product(
                root,
                breadcrumb_names=["Electronics", "Camera & Photo"],
                payload=payload,
                resolve_image=fake_resolve,
            )
            product_dir = root / "electronics" / "camera-photo" / "104001"
            self.assertTrue((product_dir / "product.json").exists())
            written = json.loads((product_dir / "product.json").read_text(encoding="utf-8"))
            self.assertEqual(written["source_id"], "104001")
            # First image = main; the rest + description images = detail.
            self.assertTrue((product_dir / "images" / "main" / "01.webp").exists())
            self.assertFalse((product_dir / "images" / "main" / "02.webp").exists())
            self.assertTrue((product_dir / "images" / "detail" / "01.webp").exists())
            self.assertTrue((product_dir / "images" / "detail" / "02.webp").exists())
            index_file = root / "electronics" / "camera-photo" / "dataset_index.jsonl"
            line = json.loads(index_file.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(line["source_id"], "104001")
            self.assertIn("product.json", line["product_json"])
            self.assertEqual(index["source_id"], "104001")

    def test_dataset_image_failure_is_recorded_not_fatal(self):
        from joybuy_crawler.dataset import save_product

        payload = {
            "source_id": "104002",
            "title": "Toaster",
            "image_urls": ["https://images3.joy-sourcing.com/product/s480x480_p/bad.png.webp"],
            "joybuy": {"breadcrumbs": [{"name": "Electronics"}]},
        }
        with tempfile.TemporaryDirectory() as tmp:

            def broken_resolve(url, timeout=30):
                raise RuntimeError("CDN 400")

            index = save_product(
                Path(tmp),
                breadcrumb_names=["Electronics"],
                payload=payload,
                resolve_image=broken_resolve,
            )
            self.assertIn("main_errors", index["images"])


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class StagingPipelineTests(CrawlerControlTestBase):
    def _pipeline(self):
        from joybuy_crawler.pipelines import StagingPipeline

        run = start_run(self.make_job(name="Pipeline job"))
        pipeline = StagingPipeline()
        pipeline.run = run
        pipeline.job = run.job
        return pipeline, run

    def _item(self, source_id="104001"):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = (
            "<html><body><h1>Kettle</h1><span class='crossOffPrice'>£29.99</span>"
            "<img src='https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp'/>"
            "</body></html>"
        )
        payload = parse_uk_product_detail(
            html, source_url=f"https://www.joybuy.co.uk/dp/k/{source_id}"
        )
        return {
            "type": "product",
            "payload": payload.to_payload(),
            "breadcrumb_names": ["Electronics", "Camera"],
            "source_url": "https://www.joybuy.co.uk/dp/k/104001",
            "structure_version": 2,
            "parser_version": "joybuy_uk.v2",
        }

    def test_process_item_passes_dataset_local_media_to_import(self):
        """dataset 的本地媒体映射必须传给导入，否则同一张图会被下载两次。"""
        pipeline, _run = self._pipeline()
        local_media = {
            "gallery": {"https://cdn.joy-sourcing.com/product/a.webp": "/tmp/a.webp"},
            "videos": {},
        }
        index_line = {
            "product_dir": "x/y/104001",
            "images": {"main": ["images/main/01.webp"], "detail": []},
            "videos": [],
            "changed": True,
            "local_media": local_media,
        }
        with (
            mock.patch("joybuy_crawler.dataset.save_product", return_value=index_line),
            mock.patch("crawler_control.import_services.import_staging_product") as importer,
        ):
            importer.return_value = mock.MagicMock(skus=[], offers=[])
            pipeline.process_item(self._item(), spider=None)

        self.assertEqual(importer.call_args.kwargs["local_media"], local_media)

    def test_process_item_imports_records_progress_and_event(self):
        pipeline, run = self._pipeline()
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            pipeline.process_item(self._item(), spider=None)

        run.refresh_from_db()
        self.assertEqual(run.downloaded_count, 1)
        self.assertEqual(run.succeeded_count, 1)
        staging = StagingProduct.objects.get(source_id="104001")
        self.assertEqual(staging.status, StagingProduct.Status.IMPORTED)
        # reused=0：dataset 下载失败时没有本地文件可复用，仍走网络（这里被 patch 成失败）。
        self.assertEqual(
            staging.imported_refs["gallery_images"],
            {"downloaded": 0, "failed": 1, "reused": 0},
        )
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="PRODUCT_IMPORTED").exists())
        from catalog.models import Spu

        self.assertTrue(Spu.objects.filter(source_identities__source_id="104001").exists())

    def test_offer_source_conflict_emits_chinese_event_and_keeps_staging_reason(self):
        """卖家名漂移导致同一来源 Offer 指向不同商家：固定事件码 + 中文提示。"""

        pipeline, run = self._pipeline()
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            pipeline.process_item(self._item(), spider=None)

        drifted = self._item()
        drifted["payload"]["source_seller_id"] = "seller-cn"
        drifted["payload"]["source_seller_name"] = "卖家 查看店铺"
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            pipeline.process_item(drifted, spider=None)

        run.refresh_from_db()
        self.assertEqual(run.succeeded_count, 1)
        self.assertEqual(run.failed_count, 1)
        event = CrawlRunEvent.objects.get(run=run, code="IMPORT_SOURCE_CONFLICT")
        self.assertIn("来源 Offer", event.message)
        self.assertIn("卖家名称/本地化", event.message)
        self.assertIn("系统不会自动改绑", event.message)
        staging = StagingProduct.objects.get(source_id="104001")
        self.assertEqual(staging.status, StagingProduct.Status.PENDING)
        self.assertIn("来源 Offer", staging.error_message)

    @staticmethod
    def _fake_spider(fatal_error="", finish_reason="finished", **attrs):
        """Scrapy 2.13 calls close_spider(spider); reason comes from stats."""

        from unittest.mock import MagicMock

        spider = MagicMock()
        spider.fatal_error = fatal_error
        spider.crawler.stats.get_stats.return_value = {"finish_reason": finish_reason}
        for name, value in attrs.items():
            setattr(spider, name, value)
        return spider

    def test_close_spider_marks_success_and_failure(self):
        from crawler_control.services import update_run_progress

        pipeline, run = self._pipeline()
        update_run_progress(run, discovered=3, downloaded=3, succeeded=3)
        pipeline.close_spider(self._fake_spider())
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.SUCCEEDED)

        pipeline2, run2 = self._pipeline()
        pipeline2.close_spider(self._fake_spider())
        run2.refresh_from_db()
        # No discovery, no success -> explicit failure with the reason event.
        self.assertEqual(run2.status, CrawlRun.Status.FAILED)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run2, code="RUN_FAILED").exists())

    def test_close_spider_reports_fatal_error(self):
        pipeline, run = self._pipeline()
        pipeline.close_spider(self._fake_spider(fatal_error="site blocked us"))
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)
        event = CrawlRunEvent.objects.filter(run=run, code="RUN_FAILED").latest("pk")
        self.assertIn("site blocked us", event.message)

    def test_close_spider_fails_when_every_product_failed(self):
        from crawler_control.services import update_run_progress

        pipeline, run = self._pipeline()
        update_run_progress(run, discovered=2, downloaded=2, failed=2)
        pipeline.close_spider(self._fake_spider())
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)

    def test_close_spider_names_network_failure_instead_of_risk_control(self):
        """2026-11-09: all listing downloads died at the TLS layer."""

        pipeline, run = self._pipeline()
        pipeline.close_spider(
            self._fake_spider(
                listing_fetch_errors=8,
                listing_error_types={
                    "ResponseNeverReceived": 6,
                    "ConnectionLost": 2,
                },
                listing_successes=0,
                last_listing_error="ResponseNeverReceived: Connection lost",
            )
        )
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)
        event = CrawlRunEvent.objects.filter(run=run, code="RUN_FAILED").latest("pk")
        self.assertIn("全部列表页请求失败", event.message)
        self.assertIn("列表页请求失败 8 次", event.message)
        self.assertIn("ResponseNeverReceived 6 次", event.message)
        self.assertIn("ConnectionLost 2 次", event.message)
        self.assertIn("VPN", event.message)
        self.assertIn("不是风控", event.message)
        self.assertNotIn("没有发现任何商品", event.message)

    def test_close_spider_keeps_generic_reason_without_download_errors(self):
        """A page that was fetched but parsed empty may still be risk/login."""

        from joybuy_crawler.pipelines import GENERIC_EMPTY_REASON

        pipeline, run = self._pipeline()
        pipeline.close_spider(self._fake_spider(listing_successes=1))
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)
        event = CrawlRunEvent.objects.filter(run=run, code="RUN_FAILED").latest("pk")
        self.assertEqual(event.message, GENERIC_EMPTY_REASON)
        self.assertIn("可能被风控拦截", event.message)

    def test_partial_listing_failure_is_reported_but_run_can_succeed(self):
        from crawler_control.services import update_run_progress

        pipeline, run = self._pipeline()
        update_run_progress(run, discovered=2, downloaded=2, succeeded=2)
        pipeline.close_spider(
            self._fake_spider(
                listing_fetch_errors=1,
                listing_error_types={"ConnectionLost": 1},
                listing_successes=1,
            )
        )
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.SUCCEEDED)
        partial = CrawlRunEvent.objects.get(run=run, code="LISTING_FETCH_PARTIAL")
        self.assertIn("1 次下载失败", partial.message)
        self.assertIn("ConnectionLost", partial.message)


class ZeroItemFailureReasonTests(unittest.TestCase):
    """The zero-product reason must name the real cause (2026-11-09)."""

    def test_download_errors_produce_network_tls_reason(self):
        from joybuy_crawler.pipelines import zero_item_failure_reason

        message = zero_item_failure_reason(
            listing_errors=2,
            error_types={"ConnectionLost": 2},
            listing_successes=0,
            robotstxt_failed=True,
            last_error="ConnectionLost: Connection to the other side was lost",
        )
        self.assertIn("全部列表页请求失败", message)
        self.assertIn("列表页请求失败 2 次", message)
        self.assertIn("ConnectionLost 2 次", message)
        self.assertIn("请检查网络、VPN 或代理", message)
        self.assertIn("不是风控", message)
        self.assertIn("robots.txt 同样无法获取", message)
        self.assertIn("最近一次错误：ConnectionLost", message)

    def test_partial_scope_when_some_listings_succeeded(self):
        from joybuy_crawler.pipelines import zero_item_failure_reason

        message = zero_item_failure_reason(
            listing_errors=1,
            error_types={"ResponseNeverReceived": 1},
            listing_successes=1,
        )
        self.assertIn("部分列表页请求失败", message)

    def test_no_download_errors_keeps_generic_reason(self):
        from joybuy_crawler.pipelines import GENERIC_EMPTY_REASON, zero_item_failure_reason

        self.assertEqual(zero_item_failure_reason(), GENERIC_EMPTY_REASON)
        # robots.txt alone is not evidence of a network failure: the listing
        # request still went out and the page was simply empty.
        self.assertEqual(
            zero_item_failure_reason(robotstxt_failed=True, listing_successes=1),
            GENERIC_EMPTY_REASON,
        )


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class ProxyConfigMiddlewareTests(unittest.TestCase):
    def test_proxy_meta_is_scheme_scoped_and_opt_in(self):
        from joybuy_crawler.middlewares import ProxyConfigMiddleware
        from scrapy.http import Request

        middleware = ProxyConfigMiddleware(
            http_proxy="127.0.0.1:7890",
            https_proxy="http://user:pass@127.0.0.1:7891",
        )
        https_request = Request("https://www.joybuy.co.uk/s?k=Phones")
        middleware.process_request(https_request, spider=None)
        self.assertEqual(https_request.meta["proxy"], "http://user:pass@127.0.0.1:7891")
        http_request = Request("http://www.joybuy.co.uk/s?k=Phones")
        middleware.process_request(http_request, spider=None)
        self.assertEqual(http_request.meta["proxy"], "http://127.0.0.1:7890")

        off = ProxyConfigMiddleware()
        direct = Request("https://www.joybuy.co.uk/s?k=Phones")
        off.process_request(direct, spider=None)
        self.assertNotIn("proxy", direct.meta)

    def test_proxy_credentials_are_redacted(self):
        from joybuy_crawler.middlewares import (
            normalize_proxy_url,
            redact_proxy_url,
        )

        self.assertEqual(
            redact_proxy_url("http://user:pass@127.0.0.1:7890"),
            "http://127.0.0.1:7890",
        )
        self.assertEqual(normalize_proxy_url("socks5://127.0.0.1:1080"), "")
        self.assertEqual(normalize_proxy_url("127.0.0.1:7890"), "http://127.0.0.1:7890")


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class ConnectivityPreflightTests(CrawlerControlTestBase):
    def test_check_connectivity_reports_transport_failure(self):
        from joybuy_crawler import runner

        with mock.patch(
            "socket.create_connection",
            side_effect=ConnectionResetError("reset by peer"),
        ):
            ok, detail = runner.check_connectivity("www.joybuy.co.uk", 443, timeout=0.1)
        self.assertFalse(ok)
        self.assertIn("ConnectionResetError", detail)

    def test_check_connectivity_closes_socket_on_success(self):
        from joybuy_crawler import runner

        connection = mock.MagicMock()
        with mock.patch("socket.create_connection", return_value=connection):
            ok, detail = runner.check_connectivity(
                "www.joybuy.co.uk", 443, timeout=0.1, use_tls=False
            )
        self.assertTrue(ok)
        self.assertEqual(detail, "")
        connection.close.assert_called_once()

    def test_proxy_endpoint_prefers_https_setting(self):
        from joybuy_crawler import runner

        self.assertEqual(
            runner._proxy_endpoint({"CRAWL_HTTPS_PROXY": "http://user:pass@127.0.0.1:7890"}),
            ("127.0.0.1", 7890),
        )
        self.assertEqual(
            runner._proxy_endpoint({"CRAWL_HTTP_PROXY": "127.0.0.1:7890"}),
            ("127.0.0.1", 7890),
        )
        self.assertIsNone(runner._proxy_endpoint({}))

    def test_unreachable_network_fails_fast_with_preflight_event(self):
        from joybuy_crawler import runner

        run = start_run(self.make_job(name="Preflight job"))
        with (
            mock.patch.object(
                runner,
                "_run_settings",
                return_value={
                    "CRAWL_PREFLIGHT_ENABLED": True,
                    "CRAWL_PREFLIGHT_TIMEOUT": 1,
                    "CRAWL_HTTPS_PROXY": "",
                    "CRAWL_HTTP_PROXY": "",
                },
            ),
            mock.patch.object(
                runner,
                "check_connectivity",
                return_value=(False, "ConnectionResetError: reset by peer"),
            ),
            mock.patch.object(runner, "CrawlerProcess") as process,
        ):
            runner.execute_run(str(run.public_id))

        process.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)
        event = CrawlRunEvent.objects.get(run=run, code="CONNECTIVITY_PREFLIGHT_FAILED")
        self.assertIn("网络不可达", event.message)
        self.assertIn("ConnectionResetError", event.message)
        self.assertIn("CRAWL_HTTPS_PROXY", event.message)


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class DetailedRunLogTests(CrawlerControlTestBase):
    """The run log must say where a product came from and where it went."""

    def test_dataset_and_import_events_carry_paths_and_ids(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail
        from joybuy_crawler.pipelines import StagingPipeline

        run = start_run(self.make_job(name="Logging job"))
        pipeline = StagingPipeline()
        pipeline.run = run
        pipeline.job = run.job

        html = (
            "<html><body><h1>Kettle</h1>"
            "<span class='crossOffPrice'>£29.99</span>"
            "<img src='https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp'/>"
            "</body></html>"
        )
        payload = parse_uk_product_detail(html, source_url="https://www.joybuy.co.uk/dp/k/104001")
        item = {
            "type": "product",
            "payload": payload.to_payload(),
            "breadcrumb_names": ["Electronics"],
            "source_url": "https://www.joybuy.co.uk/dp/k/104001",
            "structure_version": 2,
            "parser_version": "joybuy_uk.v2",
        }
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            pipeline.process_item(item, spider=None)

        saved = CrawlRunEvent.objects.get(run=run, code="DATASET_SAVED")
        self.assertIn("104001", saved.message)
        self.assertIn("var/crawl_exports/", saved.message)
        self.assertIn("product.json", saved.message)

        imported = CrawlRunEvent.objects.get(run=run, code="PRODUCT_IMPORTED")
        self.assertIn("SPU", imported.message)
        self.assertIn("SKU", imported.message)
        self.assertIn("Offer", imported.message)
        self.assertIn("暂存记录", imported.message)


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class SpiderLoggingTests(CrawlerControlTestBase):
    """The spider logs what it fetched and what it parsed.

    Regression guard for 2026-11-05: ``record_run_event`` was imported inside
    a conditional branch, which made it a function-local name that was unbound
    on the success path — every detail page raised UnboundLocalError.
    """

    def _response(self, url, html, target, latency=1.5):
        import types

        return types.SimpleNamespace(
            url=url,
            status=200,
            body=html.encode("utf-8"),
            text=html,
            meta={"target": target, "rank": 1, "download_latency": latency},
        )

    def _spider(self):
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        # 本组只断言日志文案；关掉翻页（默认开）避免 page=2 请求混入计数。
        run = start_run(self.make_job(name="Spider log job", allow_pagination=False))
        return JoybuyRunSpider(run_public_id=str(run.public_id)), run

    def test_detail_page_logs_url_fields_and_parse_summary(self):
        import types

        spider, run = self._spider()
        html = (
            "<html><body><h1>Stainless Kettle 1.7L</h1>"
            "<span class='brand'>Ochama</span>"
            "<span class='crossOffPrice'>£29.99</span>"
            "<img src='https://images4.joy-sourcing.com/product/k1.webp'/>"
            "</body></html>"
        )
        yielded = list(
            spider.parse_detail(
                self._response(
                    "https://www.joybuy.co.uk/dp/kettle/104001",
                    html,
                    spider.targets[0],
                )
            )
        )
        # 2026-11-09: the detail page hands off to the 图文详情 request first
        # (see docs/14 §7.4). This test only cares about the PC side, so the
        # flow is finished here with an empty mobile page.
        self.assertEqual(len(yielded), 1)
        request = yielded[0]
        item = next(
            iter(
                spider.parse_mobile_detail(
                    types.SimpleNamespace(
                        url=request.url,
                        status=200,
                        body=b"",
                        text="<html></html>",
                        meta=request.meta,
                    )
                )
            )
        )
        self.assertEqual(item["type"], "product")
        event = CrawlRunEvent.objects.get(run=run, code="PRODUCT_PARSED")
        self.assertIn("https://www.joybuy.co.uk/dp/kettle/104001", event.message)
        self.assertIn("104001", event.message)
        self.assertIn("29.99", event.message)
        self.assertIn("KB", event.message)

    def test_listing_page_logs_card_counts(self):
        spider, run = self._spider()
        html = (
            '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
            '<a class="style_UK_image_wrapper" href="/dp/kettle/104001">'
            '<img alt="Stainless Kettle 1.7L" src="//images4.joy-sourcing.com/k1.webp"/></a>'
            '<div class="style_title__x">Stainless Kettle 1.7L</div>'
            '<div class="style_crossOffPrice__x">£ 29 . 99</div></div></div>'
        )
        requests = list(
            spider.parse_listing(
                self._response(
                    "https://www.joybuy.co.uk/s?k=Kettles",
                    html,
                    spider.targets[0],
                )
            )
        )
        self.assertEqual(len(requests), 1)
        event = CrawlRunEvent.objects.get(run=run, code="LISTING_FETCHED")
        self.assertIn("解析出 1 张卡片", event.message)
        self.assertIn("本轮入队 1 个商品", event.message)
        self.assertEqual(spider.listing_successes, 1)
        self.assertEqual(spider.listing_fetch_errors, 0)

    def test_listing_download_failure_records_event_and_counters(self):
        """2026-11-09: a transport failure must be logged as such."""

        from scrapy.http import Request
        from twisted.python.failure import Failure

        spider, run = self._spider()
        try:
            raise ConnectionResetError("Connection to the other side was lost")
        except ConnectionResetError:
            failure = Failure()
        failure.request = Request("https://www.joybuy.co.uk/s?k=Phones")

        spider.listing_failed(failure)

        self.assertEqual(spider.listing_fetch_errors, 1)
        self.assertEqual(dict(spider.listing_error_types), {"ConnectionResetError": 1})
        self.assertEqual(spider.listing_successes, 0)
        self.assertIn("ConnectionResetError", spider.last_listing_error)

        event = CrawlRunEvent.objects.get(run=run, code="LISTING_FETCH_FAILED")
        self.assertEqual(event.level, "ERROR")
        self.assertIn("https://www.joybuy.co.uk/s?k=Phones", event.message)
        self.assertIn("ConnectionResetError", event.message)
        self.assertIn("不是风控", event.message)


class MenuJsonRoundTripNameZhTests(TestCase):
    """``--from-json`` 必须保留中文名（2026-11-11，新节点在库里没有 name_zh 可回退）。"""

    def test_json_round_trip_keeps_chinese_names(self):
        from catalog.models import SourceCategorySnapshot
        from crawler_control.management.commands.sync_joybuy_category_tree import (
            Command,
        )
        from crawler_control.tree_sync import MenuNode

        cmd = Command()
        nodes = [
            MenuNode(
                name="Pets",
                source_id="minihome:UK-Mini-HP-Pets",
                name_zh="宠物用品",
                children=[
                    MenuNode(
                        name="Cat Litter",
                        source_id="l2:4707",
                        name_zh="猫砂",
                    )
                ],
            )
        ]
        payload = cmd._nodes_to_json(nodes)
        self.assertEqual(payload[0]["name_zh"], "宠物用品")
        self.assertEqual(payload[0]["children"][0]["name_zh"], "猫砂")

        restored = cmd._json_to_nodes(payload)
        self.assertEqual(restored[0].name_zh, "宠物用品")
        self.assertEqual(restored[0].children[0].name_zh, "猫砂")

        # 写库后快照也带中文名。
        from catalog.models import SourceCatalog
        from crawler_control.tree_sync import sync_category_tree

        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system="joybuy_uk", defaults={"display_name": "Joybuy UK"}
        )
        result = sync_category_tree(catalog, restored, publish=True)
        child = SourceCategorySnapshot.objects.get(tree_version=result.tree_version, depth=1)
        self.assertEqual(child.name_zh, "猫砂")
        self.assertEqual(child.name, "Cat Litter")


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class SkipImportedProductsTests(CrawlerControlTestBase):
    """「跳过已入库」任务开关（2026-11-12）。

    开启后列表阶段先按来源身份查库，已入库商品不再产生详情页请求；
    未入库商品照常抓取，跳过数写运行事件。
    """

    LISTING = (
        '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
        '<a class="style_UK_image_wrapper" href="/dp/kettle/104001">'
        '<img alt="Kettle" src="//images4.joy-sourcing.com/k1.webp"/></a>'
        '<div class="style_title__x">Kettle</div></div></div>'
        '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
        '<a class="style_UK_image_wrapper" href="/dp/toaster/104002">'
        '<img alt="Toaster" src="//images4.joy-sourcing.com/k2.webp"/></a>'
        '<div class="style_title__x">Toaster</div></div></div>'
    )

    def _spider(self, *, skip: bool):
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        run = start_run(
            self.make_job(
                name="Skip imported job",
                product_limit=10,
                skip_imported_products=skip,
                # 本组只测「跳过已入库」，关掉翻页避免 page=2 请求混入断言。
                allow_pagination=False,
            )
        )
        return JoybuyRunSpider(run_public_id=str(run.public_id)), run

    def _response(self, spider):
        import types

        return types.SimpleNamespace(
            url="https://www.joybuy.co.uk/s?k=Kettles",
            status=200,
            body=self.LISTING.encode("utf-8"),
            text=self.LISTING,
            meta={"target": spider.targets[0], "rank": 1, "download_latency": 1.0},
        )

    def _make_imported(self, source_id="104001"):
        from catalog.product_services import get_or_create_spu_from_source

        get_or_create_spu_from_source(
            source_system="joybuy", source_id=source_id, title="Already imported"
        )

    def test_skips_imported_products_when_enabled(self):
        from crawler_control.models import CrawlRunEvent

        self._make_imported("104001")
        spider, run = self._spider(skip=True)

        requests = list(spider.parse_listing(self._response(spider)))

        self.assertEqual(len(requests), 1)
        self.assertIn("/dp/toaster/104002", requests[0].url)
        self.assertIn("104001", spider.seen_product_ids)
        self.assertEqual(spider.targets[0]["collected"], 1)
        event = CrawlRunEvent.objects.get(run=run, code="PRODUCTS_SKIPPED_IMPORTED")
        self.assertIn("跳过 1 个", event.message)

    def test_crawls_everything_when_disabled(self):
        self._make_imported("104001")
        spider, _run = self._spider(skip=False)

        requests = list(spider.parse_listing(self._response(spider)))

        self.assertEqual(len(requests), 2)
        self.assertEqual(spider.targets[0]["collected"], 2)

    def test_skips_variant_source_ids_already_bound_as_sku(self):
        """变体页（SKU 身份已绑在父 SPU 上）也要跳过，否则必然 IMPORT_SOURCE_CONFLICT。

        2026-11-25 试水：列表把同一沙发的不同尺寸变体当独立商品卡片，
        父商品导入后这些变体页各自再建 SPU → 8/50 冲突失败。
        """
        from catalog.product_services import (
            get_or_create_sku_from_source,
            get_or_create_spu_from_source,
        )
        from crawler_control.models import CrawlRunEvent

        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="104001", title="Parent sofa"
        )
        get_or_create_sku_from_source(
            spu=spu,
            source_system="joybuy",
            source_id="104002",
            specification={"Size": "King"},
            skip_attribute_validation=True,
        )
        spider, run = self._spider(skip=True)

        requests = list(spider.parse_listing(self._response(spider)))

        # 两个卡片都被跳过（一个 SPU 身份、一个 SKU 身份），无详情请求。
        self.assertEqual(requests, [])
        self.assertIn("104002", spider.seen_product_ids)
        event = CrawlRunEvent.objects.get(run=run, code="PRODUCTS_SKIPPED_IMPORTED")
        self.assertIn("跳过 2 个", event.message)

    def test_skip_flag_is_frozen_into_run_snapshot(self):
        job = self.make_job(name="Snapshot job", product_limit=5, skip_imported_products=True)
        run = start_run(job)
        self.assertTrue(run.params_snapshot["skip_imported_products"])


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class ListingPaginationTests(CrawlerControlTestBase):
    """列表翻页开关（2026-11-12，默认开）。

    开启时第一页没抓满 limit 就请求 &page=2（ robots 由 runner 关闭 OBEY）；
    关闭时保持旧行为（只抓第一屏 + LISTING_SHORTFALL）。
    """

    LISTING_PAGE = (
        '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
        '<a class="style_UK_image_wrapper" href="/dp/kettle/104001">'
        '<img alt="Kettle" src="//images4.joy-sourcing.com/k1.webp"/></a>'
        '<div class="style_title__x">Kettle</div></div></div>'
    )

    def _spider(self, *, allow_pagination: bool, product_limit: int = 10):
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        run = start_run(
            self.make_job(
                name="Pagination job",
                product_limit=product_limit,
                allow_pagination=allow_pagination,
            )
        )
        return JoybuyRunSpider(run_public_id=str(run.public_id)), run

    def _response(self, spider, html, page=1):
        import types

        return types.SimpleNamespace(
            url=f"https://www.joybuy.co.uk/s?k=Kettles&page={page}"
            if page > 1
            else "https://www.joybuy.co.uk/s?k=Kettles",
            status=200,
            body=html.encode("utf-8"),
            text=html,
            meta={"target": spider.targets[0], "page": page, "download_latency": 1.0},
        )

    def _listing(self, start_id, count=1):
        return "".join(
            self.LISTING_PAGE.replace("104001", str(start_id + index)).replace(
                "Kettle", f"Kettle {start_id + index}"
            )
            for index in range(count)
        )

    def test_pagination_enabled_yields_next_page(self):
        spider, _run = self._spider(allow_pagination=True, product_limit=10)

        requests = list(spider.parse_listing(self._response(spider, self._listing(104001))))

        # 1 个商品详情请求 + 1 个翻页请求。
        self.assertEqual(len(requests), 2)
        next_page = requests[-1]
        self.assertIn("page=2", next_page.url)
        self.assertEqual(next_page.meta["page"], 2)
        self.assertFalse(
            CrawlRunEvent.objects.filter(run=spider.run, code="LISTING_SHORTFALL").exists()
        )

    def test_pagination_disabled_keeps_single_page_and_shortfall(self):
        spider, run = self._spider(allow_pagination=False, product_limit=10)

        requests = list(spider.parse_listing(self._response(spider, self._listing(104001))))

        self.assertEqual(len(requests), 1)  # 只有商品详情请求，没有翻页。
        event = CrawlRunEvent.objects.get(run=run, code="LISTING_SHORTFALL")
        self.assertIn("未开启翻页", event.message)

    def test_duplicate_only_page_stops_pagination(self):
        spider, run = self._spider(allow_pagination=True, product_limit=10)
        spider.seen_product_ids.add("104001")

        requests = list(spider.parse_listing(self._response(spider, self._listing(104001))))

        self.assertEqual(len(requests), 0)
        event = CrawlRunEvent.objects.get(run=run, code="LISTING_SHORTFALL")
        self.assertIn("没有更多结果", event.message)

    def test_imported_only_page_keeps_paginating_with_skip_switch(self):
        """整页都是已入库商品时不能停翻页：后面页可能还有新商品。"""
        from catalog.product_services import get_or_create_spu_from_source

        spider, _run = self._spider(allow_pagination=True, product_limit=10)
        spider.skip_imported_products = True
        get_or_create_spu_from_source(
            source_system="joybuy", source_id="104001", title="Already imported"
        )

        requests = list(spider.parse_listing(self._response(spider, self._listing(104001))))

        # 详情请求被跳过（已入库），但翻页请求仍要发出。
        self.assertEqual(len(requests), 1)
        self.assertIn("page=2", requests[0].url)

    def test_pagination_cap_bounds_pages(self):
        spider, run = self._spider(allow_pagination=True, product_limit=10)
        spider._max_listing_pages = lambda: 1  # 页数上限=1 → 第一页后就不再翻。

        requests = list(spider.parse_listing(self._response(spider, self._listing(104001))))

        self.assertEqual(len(requests), 1)
        event = CrawlRunEvent.objects.get(run=run, code="LISTING_SHORTFALL")
        self.assertIn("没有更多结果", event.message)

    def test_channel_target_does_not_paginate(self):
        spider, run = self._spider(allow_pagination=True, product_limit=10)
        spider.targets[0]["pagination_base"] = ""  # minihome 频道页没有翻页基准。

        requests = list(spider.parse_listing(self._response(spider, self._listing(104001))))

        self.assertEqual(len(requests), 1)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="LISTING_SHORTFALL").exists())

    def test_runner_disables_robots_obey_for_pagination_runs(self):
        from joybuy_crawler.runner import _run_settings

        from crawler_control.services import start_run

        pagination_run = start_run(self.make_job(name="Pag on", allow_pagination=True))
        single_run = start_run(self.make_job(name="Pag off", allow_pagination=False))

        self.assertFalse(_run_settings(pagination_run)["ROBOTSTXT_OBEY"])
        self.assertTrue(_run_settings(single_run)["ROBOTSTXT_OBEY"])


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class PaginationTwoPageRelayTests(CrawlerControlTestBase):
    """翻页接力端到端模拟（2026-11-12）。

    page1 产出 page=2 请求 → 处理 page2 后因 limit 抓满而停止；
    全程事件流（LISTING_FETCHED×2、无 SHORTFALL）与 URL 形态正确。
    """

    CARD = (
        '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
        '<a class="style_UK_image_wrapper" href="/dp/k/{pid}">'
        '<img alt="K" src="//images4.joy-sourcing.com/k.webp"/></a>'
        '<div class="style_title__x">K {pid}</div></div></div>'
    )

    def _spider(self, product_limit):
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        run = start_run(
            self.make_job(name="Relay job", product_limit=product_limit, allow_pagination=True)
        )
        return JoybuyRunSpider(run_public_id=str(run.public_id)), run

    def _listing(self, start_id, count=2):
        return "".join(self.CARD.replace("{pid}", str(start_id + i)) for i in range(count))

    def _response(self, spider, page, html):
        import types

        return types.SimpleNamespace(
            url=f"https://www.joybuy.co.uk/s?k=Kettles&page={page}",
            status=200,
            body=html.encode("utf-8"),
            text=html,
            meta={"target": spider.targets[0], "page": page, "download_latency": 1.0},
        )

    def test_two_page_relay_stops_at_limit(self):
        spider, run = self._spider(product_limit=3)

        page1 = list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 2))))
        detail_urls = [r.url for r in page1 if "/dp/" in r.url]
        page2_requests = [r for r in page1 if "page=2" in r.url]
        self.assertEqual(len(detail_urls), 2)
        self.assertEqual(len(page2_requests), 1)
        self.assertTrue(page2_requests[0].url.endswith("&page=2"))

        page2 = list(spider.parse_listing(self._response(spider, 2, self._listing(104091, 2))))
        # page2 两个新商品，但 limit=3 → 只入队 1 个详情 + 不再翻页。
        detail_page2 = [r.url for r in page2 if "/dp/" in r.url]
        self.assertEqual(len(detail_page2), 1)
        self.assertFalse(any("page=3" in r.url for r in page2))
        self.assertEqual(spider.targets[0]["collected"], 3)

        fetched = CrawlRunEvent.objects.filter(run=run, code="LISTING_FETCHED")
        self.assertEqual(fetched.count(), 2)
        self.assertFalse(CrawlRunEvent.objects.filter(run=run, code="LISTING_SHORTFALL").exists())


class TargetImportedFieldTests(CrawlerControlTestBase):
    """目标入库数字段（2026-11-25）：任务字段 + 参数快照 + 校验。"""

    def test_target_stored_and_frozen_into_run_snapshot(self):
        job = self.make_job(name="Target job", product_limit=200, target_imported_count=50)
        self.assertEqual(job.target_imported_count, 50)

        run = start_run(job)

        self.assertEqual(run.params_snapshot["target_imported_count"], 50)

    def test_null_target_keeps_legacy_snapshot(self):
        job = self.make_job(name="Legacy job", product_limit=5)
        self.assertIsNone(job.target_imported_count)

        run = start_run(job)

        self.assertIsNone(run.params_snapshot["target_imported_count"])

    def test_invalid_target_rejected(self):
        from crawler_control.services import CrawlJobParamsInvalid

        for bad in (0, -1, True, "50"):
            with self.subTest(value=bad):
                with self.assertRaises(CrawlJobParamsInvalid):
                    create_crawl_job(
                        name="Bad target",
                        market=self.market,
                        source_catalog=self.catalog,
                        source_category=self.l2,
                        product_limit=10,
                        target_imported_count=bad,
                    )


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class TargetImportedPaginationTests(CrawlerControlTestBase):
    """目标入库模式（2026-11-25）：翻页看数据库里的 succeeded_count。

    旧行为按「入队候选数」停翻页（入队 50 但实际只入库 30）；目标模式下必须
    继续翻页直到 run.succeeded_count 达到 target_imported_count。
    """

    CARD = (
        '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
        '<a class="style_UK_image_wrapper" href="/dp/k/{pid}">'
        '<img alt="K" src="//images4.joy-sourcing.com/k.webp"/></a>'
        '<div class="style_title__x">K {pid}</div></div></div>'
    )

    def _spider(self, *, target, product_limit=200, allow_pagination=True):
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        run = start_run(
            self.make_job(
                name=f"Target job {target}",
                product_limit=product_limit,
                target_imported_count=target,
                allow_pagination=allow_pagination,
            )
        )
        return JoybuyRunSpider(run_public_id=str(run.public_id)), run

    def _listing(self, start_id, count):
        return "".join(self.CARD.replace("{pid}", str(start_id + i)) for i in range(count))

    def _response(self, spider, page, html):
        import types

        return types.SimpleNamespace(
            url=f"https://www.joybuy.co.uk/s?k=Kettles&page={page}",
            status=200,
            body=html.encode("utf-8"),
            text=html,
            meta={"target": spider.targets[0], "page": page, "download_latency": 1.0},
        )

    def _set_succeeded(self, run, value, failed=0):
        # 直接写库，模拟 pipeline 已经把 N 个商品导入成功（spider 必须重新读库）。
        CrawlRun.objects.filter(pk=run.pk).update(succeeded_count=value, failed_count=failed)

    def test_keeps_paginating_while_imported_below_target(self):
        """目标 5、第一页 10 个候选、只入库 2 个 → 必须继续请求 page=2。"""
        spider, run = self._spider(target=5)
        self._set_succeeded(run, 2)

        requests = list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 10))))

        detail = [r for r in requests if "/dp/" in r.url]
        next_page = [r for r in requests if "page=2" in r.url]
        # 只补缺口（5-2=3），不是把整页 10 个都拿去抓；仍继续翻页。
        self.assertEqual(len(detail), 3)
        self.assertEqual(len(next_page), 1)
        self.assertFalse(CrawlRunEvent.objects.filter(run=run, code="LISTING_SHORTFALL").exists())

    def test_throttles_enqueue_by_gap_instead_of_burning_budget(self):
        """在途已够缺口时本页不入队，但仍继续翻页等入库结果。"""
        spider, run = self._spider(target=5)
        self._set_succeeded(run, 0)

        page1 = list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 10))))
        self.assertEqual(len([r for r in page1 if "/dp/" in r.url]), 5)  # 只补 5 个
        self.assertEqual(spider.targets[0]["collected"], 5)

        # 模拟这 5 个都还在途（未入库/未失败）→ 缺口 0，不应再入队，但翻页照旧。
        page2 = list(spider.parse_listing(self._response(spider, 2, self._listing(104101, 10))))
        self.assertEqual([r for r in page2 if "/dp/" in r.url], [])
        self.assertTrue(any("page=3" in r.url for r in page2))
        self.assertEqual(spider.targets[0]["collected"], 5)

    def test_failure_frees_room_and_keeps_filling(self):
        """在途里有失败（已处理）时，缺口重新出现，可以继续入队补足。"""
        spider, run = self._spider(target=5)
        self._set_succeeded(run, 0)
        list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 5))))
        # 2 个成功、3 个失败 → pending 0，缺口 3。
        self._set_succeeded(run, 2, failed=3)
        page2 = list(spider.parse_listing(self._response(spider, 2, self._listing(104101, 10))))
        self.assertEqual(len([r for r in page2 if "/dp/" in r.url]), 3)

    def test_stops_at_target_without_requesting_next_page(self):
        """目标 3、已入库 3 个 → 停止翻页、也不再入队新候选。"""
        spider, run = self._spider(target=3)
        self._set_succeeded(run, 3)

        requests = list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 10))))

        self.assertEqual(requests, [])
        self.assertFalse(CrawlRunEvent.objects.filter(run=run, code="LISTING_SHORTFALL").exists())

    def test_shortfall_reports_target_actual_and_gap(self):
        """翻页结束时未达标：shortfall 文案含目标/实际/缺口。"""
        spider, run = self._spider(target=5)
        spider._max_listing_pages = lambda: 1  # 只能抓第一页
        self._set_succeeded(run, 2)

        list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 10))))

        event = CrawlRunEvent.objects.get(run=run, code="LISTING_SHORTFALL")
        self.assertIn("目标 5 个", event.message)
        self.assertIn("实际入库 2 个", event.message)
        self.assertIn("差 3 个", event.message)

    def test_enqueue_budget_is_four_times_target_but_not_below_product_limit(self):
        spider, _run = self._spider(target=50, product_limit=200)
        self.assertEqual(spider.enqueue_cap, 200)
        self.assertEqual(spider.targets[0]["limit"], 200)
        self.assertEqual(spider.targets[0]["target_imported"], 50)

        small, _run2 = self._spider(target=5, product_limit=2)
        self.assertEqual(small.enqueue_cap, 20)  # max(2, 5*4)

    def test_null_target_keeps_legacy_enqueue_based_pagination(self):
        """回归：target 为空时行为与旧版完全一致（按入队数停，不看入库数）。"""
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        run = start_run(self.make_job(name="No target", product_limit=3, allow_pagination=True))
        self._set_succeeded(run, 99)  # 入库数再大也不影响旧逻辑
        spider = JoybuyRunSpider(run_public_id=str(run.public_id))

        self.assertIsNone(spider.target_imported)
        self.assertEqual(spider.enqueue_cap, 3)
        self.assertIsNone(spider.targets[0]["target_imported"])

        page1 = list(spider.parse_listing(self._response(spider, 1, self._listing(104001, 2))))
        self.assertTrue(any("page=2" in r.url for r in page1))

        page2 = list(spider.parse_listing(self._response(spider, 2, self._listing(104091, 2))))
        # limit=3：第二页只入队 1 个，然后停止翻页。
        self.assertEqual(len([r for r in page2 if "/dp/" in r.url]), 1)
        self.assertFalse(any("page=3" in r.url for r in page2))


class ListingEntryFallbackTests(TestCase):
    """2026-11-16：详情页缺字段时用列表卡片数据补最小可导入 payload。"""

    def _product(self):
        from joybuy_crawler.parsers.joybuy_uk import UkProduct

        return UkProduct(
            source_id="100000000001",
            title="",
            currency="",
            current_price="",
            list_price="",
            main_price="",
            promotion_label="",
            availability="UNKNOWN",
            brand="",
            breadcrumbs=[],
            skus=[],
            gallery=[],
            description="",
            detail_images=[],
            spec_options=[],
            variants=[],
            specifications=[],
            specification_tables=[],
            content_sections=[],
            videos=[],
            seller_name="",
            seller_url="",
            rating_average=None,
            rating_count=None,
            rating_distribution={},
            rating_source="",
            ai_summary="",
            ai_summary_title="",
            ai_summary_tags=[],
            missing_fields=["title", "currency", "current_price", "skus"],
            source_url="https://www.joybuy.co.uk/dp/x/100000000001",
        )

    def test_listing_entry_fills_required_fields(self):
        from joybuy_crawler.spiders.joybuy_run import _fill_from_listing_entry

        product = self._product()
        filled = _fill_from_listing_entry(
            product,
            {
                "title": "iPhone 18 Pro 256GB",
                "original_price": "1199.00",
                "image_url": "https://images4.joy-sourcing.com/product/x.jpg",
                "source_id": "100000000001",
            },
        )
        self.assertEqual(product.title, "iPhone 18 Pro 256GB")
        self.assertEqual(product.current_price, "1199.00")
        self.assertEqual(product.currency, "GBP")
        self.assertEqual(len(product.skus), 1)
        self.assertEqual(product.skus[0]["skuId"], "100000000001")
        self.assertEqual(product.gallery, ["https://images4.joy-sourcing.com/product/x.jpg"])
        self.assertEqual(product.missing_fields, [])
        self.assertIn("title", filled)
        self.assertIn("skus", filled)

    def test_empty_entry_changes_nothing(self):
        from joybuy_crawler.spiders.joybuy_run import _fill_from_listing_entry

        product = self._product()
        before = list(product.missing_fields)
        self.assertEqual(_fill_from_listing_entry(product, {}), [])
        self.assertEqual(product.missing_fields, before)
