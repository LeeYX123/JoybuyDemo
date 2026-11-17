"""商品详情扩展数据 API（2026-11-09）：视频 / 图文区块 / 规格表格 /
spec_options / AI 摘要。"""

import shutil
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Spu, SpuDetail, SpuVideo
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from media.models import MediaAsset
from media.storage import store_bytes


class ProductDetailExtrasApiTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="joybuy-detail-media-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="extras-spu",
            title="iPhone 17 Pro 256GB",
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.spu.refresh_from_db()
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="extras-sku-1",
            specification={"系列": "256GB", "颜色": "星宇橙色"},
            skip_attribute_validation=True,
        )

    def test_detail_returns_videos_and_structured_detail(self):
        video, _ = store_bytes(
            b"fake-mp4-bytes",
            kind=MediaAsset.Kind.VIDEO,
            mime_type="video/mp4",
            source_url="https://cdn.test/v.mp4",
        )
        poster, _ = store_bytes(
            b"fake-poster-bytes",
            kind=MediaAsset.Kind.PRODUCT,
            mime_type="image/png",
            source_url="https://cdn.test/cover.png",
        )
        SpuVideo.objects.create(
            spu=self.spu,
            video=video,
            poster=poster,
            duration_ms=23000,
            source_video_id="vid-1",
            source_url="https://cdn.test/v.mp4",
            sort_order=0,
        )
        SpuDetail.objects.create(
            spu=self.spu,
            content_sections=[
                {
                    "title": "商品详情",
                    "blocks": [
                        {"type": "heading", "text": "终极 Pro 相机系统"},
                        {"type": "paragraph", "text": "三个先进的 4800 万像素后置摄像头。"},
                    ],
                    "text": "终极 Pro 相机系统\n三个先进的 4800 万像素后置摄像头。",
                    "images": ["/media/products/original/aa/bb/local.png"],
                }
            ],
            specification_tables=[
                {
                    "title": "技术规格",
                    "columns": ["属性", "值"],
                    "rows": [{"name": "型号", "value": "A3101"}],
                }
            ],
            specifications=[{"group": "技术规格", "name": "型号", "value": "A3101"}],
            spec_options=[
                {
                    "name": "系列",
                    "values": [
                        {
                            "value": "256GB",
                            "image_url": "/media/products/original/cc/dd/spec.png",
                            "sku_ids": ["extras-sku-1"],
                        }
                    ],
                }
            ],
            ai_summary="用户普遍认可相机与续航。",
            ai_summary_title="内容由人工智能总结自用户评价",
            ai_summary_tags=["拍照好", "续航强"],
        )

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 视频：本地 /media URL + 封面 + 时长 + 顺序。
        self.assertEqual(len(data["videos"]), 1)
        self.assertTrue(data["videos"][0]["url"].startswith("/media/videos/original/"))
        self.assertTrue(data["videos"][0]["poster"].startswith("/media/products/original/"))
        self.assertEqual(data["videos"][0]["duration_ms"], 23000)
        self.assertEqual(data["videos"][0]["duration"], 23.0)
        self.assertEqual(data["videos"][0]["sort_order"], 0)

        # 结构化详情原样返回，spec_options 的 sku_ids 已换成 public id。
        self.assertEqual(data["content_sections"][0]["blocks"][0]["type"], "heading")
        self.assertEqual(data["specification_tables"][0]["rows"][0]["name"], "型号")
        self.assertEqual(data["specifications"][0]["group"], "技术规格")
        self.assertEqual(data["spec_options"][0]["name"], "系列")
        self.assertEqual(
            data["spec_options"][0]["values"][0]["sku_ids"],
            [str(self.sku.public_id)],
        )
        self.assertEqual(data["ai_summary"], "用户普遍认可相机与续航。")
        self.assertEqual(data["ai_summary_tags"], ["拍照好", "续航强"])

        # 既有契约字段不变（历史商品/购物端旧逻辑仍可用）。
        for field in (
            "description",
            "category_slug",
            "category_breadcrumb",
            "skus",
            "gallery",
            "review_summary",
        ):
            self.assertIn(field, data)

    def test_historical_product_without_detail_returns_empty_structures(self):
        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["videos"], [])
        self.assertEqual(data["content_sections"], [])
        self.assertEqual(data["specification_tables"], [])
        self.assertEqual(data["specifications"], [])
        self.assertEqual(data["spec_options"], [])
        self.assertEqual(data["ai_summary"], "")
        self.assertEqual(data["ai_summary_tags"], [])
