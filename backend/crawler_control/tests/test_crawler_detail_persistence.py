"""导入端正式存储（2026-11-09）：视频本地化 + 图文区块 / 规格表格 /
spec_options / AI 摘要幂等写入。

网络下载全部用 mock 替代，测试只验证「下载 → 内容寻址落盘 → 业务表关联」
和重复导入不产生重复数据。
"""

import io
import shutil
import tempfile
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from PIL import Image

from catalog.models import SpuDetail, SpuVideo
from crawler_control.import_services import import_staging_product
from crawler_control.models import StagingProduct
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase
from media.models import MediaAsset
from media.storage import resolve_media_path


def png_bytes(color):
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buffer, format="PNG")
    return buffer.getvalue()


def image_bytes_for(url):
    seed = sum(url.encode("utf-8")) % 200
    return png_bytes((seed, (seed * 2) % 255, (seed * 3) % 255))


def video_bytes_for(url):
    return f"fake-mp4:{url}".encode("utf-8")


def detail_payload(video_id="vid-1", video_url="https://cdn.test/v1.mp4"):
    return {
        "source_id": "persist-product",
        "title": "PURE COOK 双层蒸锅",
        "currency": "GBP",
        "current_price": "29.99",
        "skus": [
            {
                "source_id": "persist-sku-1",
                "price": "29.99",
                "availability": "IN_STOCK",
                "specs": [{"name": "系列", "value": "默认"}],
            }
        ],
        "description": "核心卖点纯文本兜底。",
        "content_sections": [
            {
                "title": "产品详情",
                "blocks": [
                    {"type": "heading", "text": "安全警告"},
                    {"type": "paragraph", "text": "使用前请阅读说明书。"},
                ],
                "text": "安全警告\n使用前请阅读说明书。",
                "images": ["https://cdn.test/section-1.png", "https://cdn.test/section-2.png"],
            }
        ],
        "specifications": [
            {"group": "材质与规格", "name": "材质", "value": "不锈钢"},
            {"group": "材质与规格", "name": "用途", "value": "燃气灶"},
        ],
        "specification_tables": [
            {
                "title": "材质与规格",
                "columns": ["属性", "值"],
                "rows": [
                    {"name": "材质", "value": "不锈钢"},
                    {"name": "用途", "value": "燃气灶"},
                ],
            }
        ],
        "spec_options": [
            {
                "name": "系列",
                "values": [
                    {
                        "value": "默认",
                        "image_url": "https://cdn.test/spec.png",
                        "sku_ids": ["persist-sku-1"],
                    }
                ],
            }
        ],
        "ai_summary": "用户认可容量与做工。",
        "ai_summary_title": "内容由人工智能总结自用户评价",
        "ai_summary_tags": ["容量大", "做工好"],
        "videos": [
            {
                "url": video_url,
                "duration": 23,
                "cover": "https://cdn.test/cover.png",
                "video_id": video_id,
            }
        ],
    }


class DetailPersistenceImportTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp(prefix="joybuy-import-media-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        now = timezone.now()
        self.staging = StagingProduct.objects.create(
            source_system="joybuy",
            source_id="persist-product",
            source_url="https://www.joybuy.co.uk/dp/x/persist-product",
            payload=detail_payload(),
            first_seen_at=now,
            last_seen_at=now,
        )

    def run_import(self):
        with (
            patch(
                "crawler_control.import_services._fetch_image_bytes",
                side_effect=image_bytes_for,
            ),
            patch(
                "crawler_control.import_services._fetch_video_bytes",
                side_effect=video_bytes_for,
            ),
        ):
            return import_staging_product(self.staging, market=self.market, currency=self.currency)

    def test_import_persists_local_video_and_structured_detail(self):
        outcome = self.run_import()
        spu = outcome.spu

        detail = SpuDetail.objects.get(spu=spu)
        self.assertEqual(detail.content_sections[0]["blocks"][0]["type"], "heading")
        # 区块图片已替换成本地 /media URL，且文件真实落盘。
        for image in detail.content_sections[0]["images"]:
            self.assertTrue(image.startswith("/media/products/original/"))
            relative = image[len("/media/") :]
            self.assertTrue(resolve_media_path(relative).is_file())
        self.assertEqual(detail.specification_tables[0]["title"], "材质与规格")
        self.assertEqual(
            [row["name"] for row in detail.specification_tables[0]["rows"]],
            ["材质", "用途"],
        )
        self.assertTrue(
            detail.spec_options[0]["values"][0]["image_url"].startswith("/media/products/original/")
        )
        self.assertEqual(detail.ai_summary, "用户认可容量与做工。")
        self.assertEqual(detail.ai_summary_tags, ["容量大", "做工好"])

        video = SpuVideo.objects.get(spu=spu)
        self.assertEqual(video.source_video_id, "vid-1")
        self.assertEqual(video.duration_ms, 23000)
        self.assertEqual(video.video.kind, MediaAsset.Kind.VIDEO)
        self.assertTrue(video.video.relative_path.startswith("videos/original/"))
        self.assertTrue(resolve_media_path(video.video.relative_path).is_file())
        self.assertIsNotNone(video.poster_id)
        self.assertTrue(video.poster.relative_path.startswith("products/original/"))

        self.assertEqual(self.staging.status, StagingProduct.Status.IMPORTED)
        self.assertEqual(self.staging.imported_refs["videos"]["downloaded"], 1)
        self.assertEqual(self.staging.imported_refs["detail"]["content_sections"], 1)

    def test_reimport_is_idempotent(self):
        first = self.run_import()
        video_pk = SpuVideo.objects.get(spu=first.spu).pk
        asset_count = MediaAsset.objects.count()

        second = self.run_import()

        self.assertEqual(first.spu.pk, second.spu.pk)
        self.assertEqual(SpuDetail.objects.count(), 1)
        self.assertEqual(SpuVideo.objects.count(), 1)
        self.assertEqual(SpuVideo.objects.get(spu=first.spu).pk, video_pk)
        # 相同字节内容寻址：重复导入不新增媒体资产。
        self.assertEqual(MediaAsset.objects.count(), asset_count)
        self.assertTrue(first.spu.detail.content_sections[0]["images"][0].startswith("/media/"))

    def test_empty_payload_does_not_wipe_existing_detail_or_videos(self):
        outcome = self.run_import()
        original_sections = outcome.spu.detail.content_sections

        # 旧版/失败解析的 payload：没有 content_sections / videos 键。
        self.staging.payload = {
            "source_id": "persist-product",
            "title": "PURE COOK 双层蒸锅",
            "currency": "GBP",
            "current_price": "29.99",
            "skus": [
                {
                    "source_id": "persist-sku-1",
                    "price": "29.99",
                    "availability": "IN_STOCK",
                    "specs": [{"name": "系列", "value": "默认"}],
                }
            ],
        }
        self.staging.save(update_fields=["payload", "updated_at"])
        self.run_import()

        outcome.spu.refresh_from_db()
        self.assertEqual(outcome.spu.detail.content_sections, original_sections)
        self.assertEqual(SpuVideo.objects.filter(spu=outcome.spu).count(), 1)

    def test_manual_content_sections_survive_reimport_but_other_fields_refresh(self):
        """管理端人工编辑的图文区块（content_source=manual）不被爬虫覆盖。

        规格表格 / spec_options / AI 等其它字段照常刷新（docs/14 §9.9）。
        """

        outcome = self.run_import()
        spu = outcome.spu
        detail = SpuDetail.objects.get(spu=spu)
        # 正常导入默认 crawler 来源。
        self.assertEqual(detail.content_source, SpuDetail.ContentSource.CRAWLER)

        manual_sections = [
            {
                "title": "人工区块",
                "blocks": [{"type": "paragraph", "text": "运营手写内容，不许被爬虫覆盖。"}],
                "images": [],
            }
        ]
        detail.content_sections = manual_sections
        detail.content_source = SpuDetail.ContentSource.MANUAL
        detail.save(update_fields=["content_sections", "content_source"])

        # 重导：payload 带全新的 content_sections 与更新过的 specifications
        # （不带 specification_tables，让后端按新 specifications 兜底生成表格）。
        payload = dict(self.staging.payload)
        payload["content_sections"] = [
            {
                "title": "爬虫新区块",
                "blocks": [{"type": "paragraph", "text": "爬虫解析到的图文内容。"}],
                "text": "爬虫解析到的图文内容。",
                "images": ["https://cdn.test/section-new.png"],
            }
        ]
        payload["specifications"] = [{"group": "技术规格", "name": "型号", "value": "X100"}]
        payload.pop("specification_tables", None)
        self.staging.payload = payload
        self.staging.save(update_fields=["payload", "updated_at"])
        self.run_import()

        detail.refresh_from_db()
        self.assertEqual(detail.content_source, SpuDetail.ContentSource.MANUAL)
        # 人工图文区块原样保留。
        self.assertEqual(detail.content_sections, manual_sections)
        # 其它爬虫字段照常刷新。
        self.assertEqual(detail.specifications[0]["name"], "型号")
        self.assertEqual(detail.specification_tables[0]["title"], "技术规格")
        self.assertEqual(detail.specification_tables[0]["rows"][0]["value"], "X100")

    def test_video_removed_from_source_is_deleted(self):
        self.run_import()

        self.staging.payload = detail_payload(video_id="vid-2", video_url="https://cdn.test/v2.mp4")
        self.staging.save(update_fields=["payload", "updated_at"])
        outcome = self.run_import()

        rows = list(SpuVideo.objects.filter(spu=outcome.spu))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source_video_id, "vid-2")
        self.assertEqual(rows[0].source_url, "https://cdn.test/v2.mp4")
