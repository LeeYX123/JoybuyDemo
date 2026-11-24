"""``sync_channel_modules`` 针对性测试（真站楼层 → ChannelModule 同步）。

红线：
1. 首次同步按 JSON 顺序建楼层与位次；楼层匹配先 sort_order 再 title 兜底；
2. 同一份 payload 重跑幂等（行数不变、商品行不重建）；
3. 同 payload 里重复楼层按 (title_en, 有序 skuId) 去重；
4. 解析不到 / 不可售的 SKU 进缺失清单并写出 missing_skus.json；
5. 本地多余楼层只 enabled=False，绝不删除；
6. --dry-run 零写操作；--channel 只影响指定频道；
7. payload 三种顶层形态都接受：旧 ``[{channel_code, modules}]`` 数组、
   ``{"channels": [...]}`` 包装、真站产物的 slug-dict（``_meta`` 等非频道键跳过）；
8. 2026-11-24 起位次按 SKU 唯一：同 SPU 不同 SKU 各占一条（SKU 身份优先），
   可售按该 SKU 自己的 Offer 判断，SKU 解析不到才退回 SPU 级位次（sku=NULL）。

不访问真站，全部数据在内存 + tmp 文件里造。
"""

import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
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

    def add_variant(
        self,
        spu,
        suffix: str,
        *,
        price="19.99",
        offer_status=Offer.Status.ACTIVE,
        sku_status=Sku.Status.ACTIVE,
    ):
        """给已有 SPU 追加一个尺码/颜色（独立 SKU 身份 + 自己的 Offer）。"""

        sku = Sku.objects.create(
            spu=spu,
            specification={"size": suffix},
            specification_signature=f"sig-{suffix}",
            status=sku_status,
        )
        now = timezone.now()
        SkuSourceIdentity.objects.create(
            sku=sku,
            source_system=SOURCE_SYSTEM,
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
                current_price=Decimal(price),
                status=offer_status,
            )
        return sku

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

    def module_pairs(self, module: ChannelModule) -> list[tuple[int, int | None]]:
        return list(module.items.order_by("sort_order", "pk").values_list("spu_id", "sku_id"))

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

    # --- 按 SKU 唯一（2026-11-24） ---------------------------------------
    def test_same_spu_variants_each_get_a_position(self):
        """同一 SPU 的不同 SKU 各占一条位次（真站楼层按尺码重复展示）。"""

        spu, _base_sku = self.make_product("1")
        blue = self.add_variant(spu, "1-blue", price="12.50")
        red = self.add_variant(spu, "1-red", price="15.00")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Buy more save more",
                            "sort_order": 0,
                            "items": [
                                {"skuId": "sku-1-blue", "spuId": "spu-1", "title": "Blue"},
                                {"skuId": "sku-1-red", "spuId": "spu-1", "title": "Red"},
                                # 完全相同的 (spu, sku) 只留第一条。
                                {"skuId": "sku-1-blue", "spuId": "spu-1", "title": "Blue again"},
                            ],
                        }
                    ],
                }
            ]
        )

        output = self.run_command(payload)

        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(self.module_pairs(module), [(spu.pk, blue.pk), (spu.pk, red.pk)])
        self.assertEqual(ChannelModuleProduct.objects.filter(module=module).count(), 2)
        self.assertIn("products written=2", output)

    def test_sku_level_sellability_filters_only_that_variant(self):
        """SKU 级可售：该 SKU 的 Offer 非 ACTIVE 时该位次不写，同 SPU 其它尺码保留。"""

        spu, _base_sku = self.make_product("1")  # SPU 本身有 ACTIVE Offer
        live = self.add_variant(spu, "1-live", price="20.00")
        self.add_variant(spu, "1-draft", offer_status=Offer.Status.DRAFT)
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [
                                {"skuId": "sku-1-live", "spuId": "spu-1", "title": "Live"},
                                {"skuId": "sku-1-draft", "spuId": "spu-1", "title": "Draft"},
                            ],
                        }
                    ],
                }
            ]
        )

        self.run_command(payload)

        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(self.module_pairs(module), [(spu.pk, live.pk)])
        report = json.loads(self.missing_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {(entry["skuId"], entry["reason"]) for entry in report["missing"]},
            {("sku-1-draft", "not_sellable")},
        )

    def test_sku_positions_are_idempotent(self):
        spu, _base_sku = self.make_product("1")
        first = self.add_variant(spu, "1-a", price="11.00")
        second = self.add_variant(spu, "1-b", price="12.00")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [
                                {"skuId": "sku-1-a", "spuId": "spu-1"},
                                {"skuId": "sku-1-b", "spuId": "spu-1"},
                            ],
                        }
                    ],
                }
            ]
        )
        self.run_command(payload)
        module = ChannelModule.objects.get(channel_code=CHANNEL)
        item_pks = list(
            ChannelModuleProduct.objects.filter(module=module)
            .order_by("sort_order")
            .values_list("pk", flat=True)
        )

        output = self.run_command(payload)

        self.assertEqual(
            list(
                ChannelModuleProduct.objects.filter(module=module)
                .order_by("sort_order")
                .values_list("pk", flat=True)
            ),
            item_pks,
        )
        self.assertEqual(self.module_pairs(module), [(spu.pk, first.pk), (spu.pk, second.pk)])
        self.assertIn("new=0 updated=0 unchanged=1 disabled=0", output)
        self.assertIn("products written=0", output)

    def test_variant_swap_is_detected_as_change(self):
        """序列比较必须含 sku：两个尺码互换位置要重建，不能算「未变」。"""

        spu, _base_sku = self.make_product("1")
        first = self.add_variant(spu, "1-a", price="11.00")
        second = self.add_variant(spu, "1-b", price="12.00")

        def payload_with(order):
            return self.write_payload(
                [
                    {
                        "channel_code": CHANNEL,
                        "modules": [
                            {
                                "title_en": "Best sellers",
                                "sort_order": 0,
                                "items": [
                                    {"skuId": f"sku-1-{suffix}", "spuId": "spu-1"}
                                    for suffix in order
                                ],
                            }
                        ],
                    }
                ]
            )

        self.run_command(payload_with(["a", "b"]))
        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(self.module_pairs(module), [(spu.pk, first.pk), (spu.pk, second.pk)])

        output = self.run_command(payload_with(["b", "a"]))

        module.refresh_from_db()
        self.assertEqual(self.module_pairs(module), [(spu.pk, second.pk), (spu.pk, first.pk)])
        self.assertIn("updated=1", output)
        self.assertIn("products written=2", output)

    def test_unresolved_sku_falls_back_to_spu_level_position(self):
        """解析不到本地 SKU 时退回 SPU 级位次（sku=NULL），与旧版一致。"""

        spu, _sku = self.make_product("1")
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "Best sellers",
                            "sort_order": 0,
                            "items": [{"skuId": "sku-ghost", "spuId": "spu-1", "title": "Ghost"}],
                        }
                    ],
                }
            ]
        )

        self.run_command(payload)

        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(self.module_pairs(module), [(spu.pk, None)])

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

    def test_removed_middle_floor_is_the_only_one_disabled(self):
        # 真站中间楼层下线后，后面楼层位置整体前移。按位置先匹配会把后续楼层逐行改名，
        # 并误停用仍在线的最后一层（健康频道 Value Bundles / Performance Tech 真实案例）。
        _spu_first, _sku_first = self.make_product("first")
        spu_third, _sku_third = self.make_product("third")
        first = ChannelModule.objects.create(
            channel_code=CHANNEL, title_en="First floor", sort_order=0, enabled=True
        )
        gone = ChannelModule.objects.create(
            channel_code=CHANNEL, title_en="Value Bundles", sort_order=1, enabled=True
        )
        third = ChannelModule.objects.create(
            channel_code=CHANNEL, title_en="Third floor", sort_order=2, enabled=True
        )
        payload = self.write_payload(
            [
                {
                    "channel_code": CHANNEL,
                    "modules": [
                        {
                            "title_en": "First floor",
                            "sort_order": 0,
                            "items": [{"skuId": "sku-first"}],
                        },
                        {
                            "title_en": "Third floor",
                            "sort_order": 1,
                            "items": [{"skuId": "sku-third"}],
                        },
                    ],
                }
            ]
        )

        output = self.run_command(payload)

        gone.refresh_from_db()
        third.refresh_from_db()
        first.refresh_from_db()
        # 被停用的就是下线的那一层，且保留原标题（不删除、不被改名）。
        self.assertFalse(gone.enabled)
        self.assertEqual(gone.title_en, "Value Bundles")
        self.assertEqual(gone.sort_order, 1)
        self.assertEqual(third.sort_order, 2)
        # 仍在线的楼层保持自己的身份；被停用楼层占住的序号不抢，最终位置顺延保留。
        self.assertTrue(third.enabled)
        self.assertEqual(third.title_en, "Third floor")
        self.assertEqual(third.sort_order, 2)
        self.assertEqual(self.module_items(third), [spu_third.pk])
        self.assertTrue(first.enabled)
        self.assertEqual(first.sort_order, 0)
        self.assertIn("updated=2", output)
        self.assertIn("disabled=1", output)

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

    # --- payload 形态适配（真站 slug-dict / 旧数组 / 畸形键） ---------------
    def test_slug_dict_payload_is_adapted_and_meta_skipped(self):
        # 真站 floors_live.json 顶层是 {slug: {code, floors}, "_meta": {...}}。
        spu_one, _sku_one = self.make_product("1")
        spu_two, _sku_two = self.make_product("2")
        payload = self.tmp / "floors_live.json"
        payload.write_text(
            json.dumps(
                {
                    "beauty-personal-care": {
                        "code": CHANNEL,
                        "floor_count": 1,
                        "item_total": 2,
                        "missing_item_fields": [],
                        "floors": [
                            {
                                "title_en": "Best sellers",
                                "title_zh": "爆品热销",
                                "sort_order": 0,
                                "item_count": 2,
                                "items": [
                                    {
                                        "skuId": "sku-1",
                                        "spuId": "spu-1",
                                        "title": "One",
                                        # 真站多余字段（价格/库存/类目）必须被忽略。
                                        "mainPrice": "9.99",
                                        "inStock": True,
                                        "categoryId1": "4909",
                                    },
                                    {"skuId": "sku-2", "spuId": "spu-2", "title": "Two"},
                                ],
                            }
                        ],
                    },
                    "pet-supplies": {
                        "code": OTHER_CHANNEL,
                        "floor_count": 1,
                        "item_total": 1,
                        "floors": [
                            {
                                "title_en": "Pets picks",
                                "sort_order": 0,
                                "items": [{"skuId": "sku-2", "spuId": "spu-2"}],
                            }
                        ],
                    },
                    "_meta": {"generated_at": "2026-11-23", "note": "not a channel"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        output = self.run_command(payload)

        module = ChannelModule.objects.get(channel_code=CHANNEL)
        self.assertEqual(module.title_en, "Best sellers")
        self.assertEqual(module.title_zh, "爆品热销")
        self.assertEqual(module.sort_order, 0)
        self.assertEqual(self.module_items(module), [spu_one.pk, spu_two.pk])
        other = ChannelModule.objects.get(channel_code=OTHER_CHANNEL)
        self.assertEqual(other.title_en, "Pets picks")
        self.assertEqual(self.module_items(other), [spu_two.pk])
        self.assertEqual(ChannelModule.objects.count(), 2)
        self.assertIn("skipped 1 non-channel key(s)", output)
        self.assertIn("_meta", output)

    def test_list_and_channels_wrapper_payloads_still_load(self):
        # 旧契约：convert_floors.py 产出的数组；以及 {"channels": [...]} 包装。
        entries = [{"channel_code": CHANNEL, "modules": [{"title_en": "A", "items": []}]}]
        list_path = self.tmp / "list.json"
        list_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        wrapper_path = self.tmp / "wrapper.json"
        wrapper_path.write_text(
            json.dumps({"channels": entries}, ensure_ascii=False), encoding="utf-8"
        )

        self.assertEqual(sync_module.load_payload(list_path), entries)
        self.assertEqual(sync_module.load_payload(wrapper_path), entries)

    def test_malformed_slug_dict_keys_are_skipped_not_fatal(self):
        self.make_product("1")
        payload = self.tmp / "mixed.json"
        payload.write_text(
            json.dumps(
                {
                    "_meta": {"generated_at": "2026-11-23"},
                    "notes": "captured by hand",
                    "broken": ["not", "a", "dict"],
                    "no-code": {"floors": [{"title_en": "Ghost"}]},
                    "no-floors": {"code": "UK-Mini-HP-Ghost"},
                    "bad-floors": {"code": "UK-Mini-HP-Bad", "floors": "nope"},
                    "pet-supplies": {
                        "code": OTHER_CHANNEL,
                        "floors": [
                            {
                                "title_en": "Pets picks",
                                "sort_order": 0,
                                "items": [{"skuId": "sku-1", "spuId": "spu-1"}],
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        output = self.run_command(payload)

        self.assertEqual(ChannelModule.objects.filter(channel_code=OTHER_CHANNEL).count(), 1)
        # 6 个畸形键被跳过（_meta / notes / broken / no-code / no-floors / bad-floors）。
        self.assertIn("skipped 6 non-channel key(s)", output)

    def test_slug_dict_without_any_channel_raises_command_error(self):
        path = self.tmp / "meta_only.json"
        path.write_text(json.dumps({"_meta": {"generated_at": "2026-11-23"}}), encoding="utf-8")

        with self.assertRaises(CommandError):
            sync_module.load_payload(path)
