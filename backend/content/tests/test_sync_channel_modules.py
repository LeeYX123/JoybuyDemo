"""``sync_channel_modules`` 针对性测试（真站楼层 → ChannelModule 同步）。

红线：
1. 首次同步按 JSON 顺序建楼层与位次；楼层匹配先 sort_order 再 title 兜底；
2. 同一份 payload 重跑幂等（行数不变、商品行不重建）；
3. 同 payload 里重复楼层按 (title_en, 有序 skuId) 去重；
4. 解析不到 / 不可售的 SKU 进缺失清单并写出 missing_skus.json；
5. 本地多余楼层只 enabled=False，绝不删除；
6. --dry-run 零写操作；--channel 只影响指定频道。

不访问真站，全部数据在内存 + tmp 文件里造。
"""

import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import Sku, SkuSourceIdentity, Spu, SpuSourceIdentity
from content.management.commands import sync_channel_modules as sync_module
from content.models import ChannelModule, ChannelModuleProduct
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market, Offer

CHANNEL = "UK-Mini-HP-Beauty"
OTHER_CHANNEL = "UK-Mini-HP-Pets"
SOURCE_SYSTEM = "joybuy_uk"


class SyncChannelModulesTests(TestCase):
    def setUp(self):
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.currency = Currency.objects.get(code="GBP")
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = Path(self.tmpdir.name)
        self.missing_path = self.tmp / "missing_skus.json"

    # --- fixtures -------------------------------------------------------
    def make_product(
        self,
        suffix: str,
        *,
        spu_status=Spu.Status.ACTIVE,
        sku_status=Sku.Status.ACTIVE,
        offer_status=Offer.Status.ACTIVE,
        with_spu_identity=True,
        with_sku_identity=True,
        source_system=SOURCE_SYSTEM,
    ):
        spu = Spu.objects.create(status=spu_status)
        sku = Sku.objects.create(
            spu=spu,
            specification={},
            specification_signature=f"sig-{suffix}",
            status=sku_status,
        )
        now = timezone.now()
        if with_spu_identity:
            SpuSourceIdentity.objects.create(
                spu=spu,
                source_system=source_system,
                source_id=f"spu-{suffix}",
                first_seen_at=now,
                last_seen_at=now,
            )
        if with_sku_identity:
            SkuSourceIdentity.objects.create(
                sku=sku,
                source_system=source_system,
                source_id=f"sku-{suffix}",
                first_seen_at=now,
                last_seen_at=now,
            )
        if offer_status is not None:
            Offer.objects.create(
                merchant=self.merchant,
                sku=sku,
                market=self.market,
                currency=self.currency,
                current_price=Decimal("9.99"),
                status=offer_status,
            )
        return spu, sku

    def write_payload(self, channels) -> Path:
        path = self.tmp / "floors_live.json"
        path.write_text(json.dumps(channels, ensure_ascii=False), encoding="utf-8")
        return path

    def run_command(self, payload: Path, *extra: str) -> str:
        out = StringIO()
        call_command(
            "sync_channel_modules",
            "--source",
            str(payload),
            "--missing-report",
            str(self.missing_path),
            *extra,
            stdout=out,
            stderr=StringIO(),
        )
        return out.getvalue()

    def module_items(self, module: ChannelModule) -> list[int]:
        return list(module.items.order_by("sort_order", "pk").values_list("spu_id", flat=True))

    # --- tests -----------------------------------------------------------
    def test_first_sync_creates_floors_and_product_order(self):
        spu_one, _sku_one = self.make_product("1")
        spu_two, _sku_two = self.make_product("2", with_spu_identity=False)
        spu_three, _sku_three = self.make_product("3")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "title_zh": "爆品热销",
                            "sort_order": 0,
                            "items": [
                                # 只有 SKU 身份（spuId 缺失）→ 退化为 skuId 查。
                                {"skuId": "sku-2", "title": "Second"},
                                # 只有 SPU 身份，skuId 在本地不存在 → 走 SPU 身份。
                                {"skuId": "unknown-sku", "spuId": "spu-1", "title": "First"},
                            ],
                        },
                        {
                            "title_en": "New arrivals",
                            "sort_order": 1,
                            "items": [
                                # spuId 与 skuId 都存在，SKU 身份也应能解析。
                                {"skuId": "sku-3", "spuId": "spu-3", "title": "Third"},
                            ],
                        },
                    ],
                }
            ]
        )

        output = self.run_command(payload)

        modules = list(ChannelModule.objects.filter(channel_code=CHANNEL).order_by("sort_order"))
        self.assertEqual(len(modules), 2)
        self.assertEqual(modules[0].title_en, "Best sellers")
        self.assertEqual(modules[0].title_zh, "爆品热销")
        self.assertEqual(modules[0].sort_order, 0)
        self.assertTrue(modules[0].enabled)
        self.assertEqual(self.module_items(modules[0]), [spu_two.pk, spu_one.pk])
        self.assertEqual(modules[1].title_en, "New arrivals")
        self.assertEqual(self.module_items(modules[1]), [spu_three.pk])
        self.assertIn("new=2", output)
        self.assertIn("products written=3", output)

    def test_rerun_same_payload_is_idempotent(self):
        self.make_product("1")
        self.make_product("2")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [{"skuId": "sku-1"}, {"skuId": "sku-2"}],
                        }
                    ],
                }
            ]
        )
        self.run_command(payload)
        module = ChannelModule.objects.get(channel_code=CHANNEL)
        module_pk = module.pk
        item_pks = list(
            ChannelModuleProduct.objects.filter(module=module)
            .order_by("sort_order")
            .values_list("pk", flat=True)
        )

        output = self.run_command(payload)

        self.assertEqual(ChannelModule.objects.filter(channel_code=CHANNEL).count(), 1)
        self.assertEqual(ChannelModule.objects.get(channel_code=CHANNEL).pk, module_pk)
        self.assertEqual(
            list(
                ChannelModuleProduct.objects.filter(module=module)
                .order_by("sort_order")
                .values_list("pk", flat=True)
            ),
            item_pks,
        )
        self.assertIn("new=0 updated=0 unchanged=1 disabled=0", output)
        self.assertIn("products written=0", output)

    def test_duplicate_floors_are_deduped_by_title_and_sku_sequence(self):
        self.make_product("1")
        floor = {
            "title_en": "Best sellers",
            "title_zh": "爆品热销",
            "sort_order": 0,
            "items": [{"skuId": "sku-1", "title": "One"}],
        }
        payload = self.write_payload(
            [{"channel_code": CHANNEL, "modules": [floor, dict(floor), dict(floor), dict(floor)]}]
        )

        output = self.run_command(payload)

        modules = ChannelModule.objects.filter(channel_code=CHANNEL)
        self.assertEqual(modules.count(), 1)
        self.assertEqual(ChannelModuleProduct.objects.filter(module=modules.first()).count(), 1)
        self.assertIn("duplicate floors dropped=3", output)

    def test_missing_skus_are_reported_and_written_to_json(self):
        spu_one, _ = self.make_product("1")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [
                                {"skuId": "sku-1", "title": "Known"},
                                {"skuId": "sku-ghost", "title": "Ghost product"},
                            ],
                        }
                    ],
                }
            ]
        )

        output = self.run_command(payload)

        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(self.module_items(module), [spu_one.pk])
        report = json.loads(self.missing_path.read_text(encoding="utf-8"))
        self.assertEqual(report["total_missing"], 1)
        entry = report["missing"][0]
        self.assertEqual(entry["skuId"], "sku-ghost")
        self.assertEqual(entry["title"], "Ghost product")
        self.assertEqual(entry["channel_code"], CHANNEL)
        self.assertEqual(entry["reason"], "spu_not_found")
        self.assertIn("sku-ghost", output)

    def test_unsellable_spu_is_reported_not_linked(self):
        # 可售三条件：Offer DRAFT 的 SPU 解析得到也不能进楼层（前台会 404）。
        self.make_product("draft-offer", offer_status=Offer.Status.DRAFT)
        self.make_product("inactive-sku", sku_status=Sku.Status.INACTIVE)
        self.make_product("draft-spu", spu_status=Spu.Status.DRAFT)
        ok_spu, _ = self.make_product("ok")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [
                                {"skuId": "sku-ok", "title": "OK"},
                                {"skuId": "sku-draft-offer", "title": "Draft offer"},
                                {"skuId": "sku-inactive-sku", "title": "Inactive sku"},
                                {"skuId": "sku-draft-spu", "title": "Draft spu"},
                            ],
                        }
                    ],
                }
            ]
        )

        self.run_command(payload)

        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(self.module_items(module), [ok_spu.pk])
        report = json.loads(self.missing_path.read_text(encoding="utf-8"))
        reasons = {(entry["skuId"], entry["reason"]) for entry in report["missing"]}
        self.assertEqual(
            reasons,
            {
                ("sku-draft-offer", "not_sellable"),
                ("sku-inactive-sku", "not_sellable"),
                ("sku-draft-spu", "not_sellable"),
            },
        )

    def test_local_extra_floors_are_disabled_not_deleted(self):
        self.make_product("1")
        legacy = ChannelModule.objects.create(
            channel_code=CHANNEL,
            title_en="Legacy floor",
            title_zh="旧楼层",
            sort_order=9,
        )
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [{"skuId": "sku-1"}],
                        }
                    ],
                }
            ]
        )

        output = self.run_command(payload)

        legacy.refresh_from_db()
        self.assertTrue(ChannelModule.objects.filter(pk=legacy.pk).exists())
        self.assertFalse(legacy.enabled)
        self.assertEqual(legacy.title_zh, "旧楼层")
        self.assertIn("disabled=1", output)

    def test_dry_run_changes_nothing_in_database(self):
        old_spu, _ = self.make_product("old")
        self.make_product("1")
        self.make_product("2")
        old_module = ChannelModule.objects.create(
            channel_code=CHANNEL,
            title_en="Old title",
            title_zh="旧标题",
            sort_order=0,
            enabled=True,
        )
        ChannelModuleProduct.objects.create(module=old_module, spu=old_spu, sort_order=0)
        legacy = ChannelModule.objects.create(
            channel_code=CHANNEL,
            title_en="Legacy floor",
            sort_order=7,
            enabled=True,
        )
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "title_zh": "爆品热销",
                            "sort_order": 0,
                            "items": [{"skuId": "sku-1"}, {"skuId": "sku-2"}],
                        }
                    ],
                }
            ]
        )

        output = self.run_command(payload, "--dry-run")

        self.assertEqual(ChannelModule.objects.filter(channel_code=CHANNEL).count(), 2)
        old_module.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual(old_module.title_en, "Old title")
        self.assertEqual(old_module.title_zh, "旧标题")
        self.assertTrue(old_module.enabled)
        self.assertTrue(legacy.enabled)
        self.assertEqual(self.module_items(old_module), [old_spu.pk])
        self.assertEqual(ChannelModuleProduct.objects.count(), 1)
        self.assertIn("DRY RUN", output)
        self.assertIn("products planned=2", output)
        # dry-run 也要产出缺失清单文件（本次没有缺失，文件仍写）。
        self.assertTrue(self.missing_path.is_file())

    def test_channel_filter_only_touches_selected_channel(self):
        self.make_product("1")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {"title_en": "Best sellers", "sort_order": 0, "items": [{"skuId": "sku-1"}]}
                    ],
                },
                {
                    "channel_code": OTHER_CHANNEL,
                    "modules": [
                        {"title_en": "Pets picks", "sort_order": 0, "items": [{"skuId": "sku-1"}]}
                    ],
                },
            ]
        )

        output = self.run_command(payload, "--channel", CHANNEL)

        self.assertEqual(ChannelModule.objects.filter(channel_code=CHANNEL).count(), 1)
        self.assertEqual(ChannelModule.objects.filter(channel_code=OTHER_CHANNEL).count(), 0)
        self.assertIn(CHANNEL, output)
        self.assertNotIn(f"[{OTHER_CHANNEL}]", output)

    def test_failing_channel_does_not_block_other_channels(self):
        self.make_product("1")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {"title_en": "Best sellers", "sort_order": 0, "items": [{"skuId": "sku-1"}]}
                    ],
                },
                {
                    "channel_code": OTHER_CHANNEL,
                    "modules": [
                        {"title_en": "Pets picks", "sort_order": 0, "items": [{"skuId": "sku-1"}]}
                    ],
                },
            ]
        )
        original = sync_module.sync_channel

        def flaky(channel_code, planned, *, dry_run):
            if channel_code == CHANNEL:
                raise RuntimeError("boom")
            return original(channel_code, planned, dry_run=dry_run)

        with mock.patch.object(sync_module, "sync_channel", side_effect=flaky):
            output = self.run_command(payload)

        self.assertEqual(ChannelModule.objects.filter(channel_code=CHANNEL).count(), 0)
        self.assertEqual(ChannelModule.objects.filter(channel_code=OTHER_CHANNEL).count(), 1)
        self.assertIn(f"[{CHANNEL}] FAILED: RuntimeError: boom", output)
        report = json.loads(self.missing_path.read_text(encoding="utf-8"))
        self.assertEqual(report["failures"][0]["channel_code"], CHANNEL)

    def test_title_fallback_matches_existing_floor_when_sort_order_moves(self):
        old_spu, _ = self.make_product("old")
        new_spu, _ = self.make_product("new")
        module = ChannelModule.objects.create(
            channel_code=CHANNEL,
            title_en="Best sellers",
            title_zh="爆品热销",
            sort_order=5,
            enabled=False,
        )
        ChannelModuleProduct.objects.create(module=module, spu=old_spu, sort_order=0)
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "title_zh": "爆品热销",
                            "sort_order": 0,
                            "items": [{"skuId": "sku-new"}],
                        }
                    ],
                }
            ]
        )

        output = self.run_command(payload)

        self.assertEqual(ChannelModule.objects.filter(channel_code=CHANNEL).count(), 1)
        module.refresh_from_db()
        self.assertEqual(module.sort_order, 0)
        self.assertTrue(module.enabled)
        self.assertEqual(self.module_items(module), [new_spu.pk])
        self.assertIn("new=0 updated=1", output)
