"""批次 DB：建同款族（默认 DRY_RUN；``--apply`` 才写库）。

用法::

    .venv/Scripts/python.exe backend/manage.py build_variant_families                 # 只打印计划
    .venv/Scripts/python.exe backend/manage.py build_variant_families --apply         # 写库
    .venv/Scripts/python.exe backend/manage.py build_variant_families --apply --report var/...json

规则全部在 ``catalog/variant_family_services.py``（与 ``var/`` 下预览脚本同源）：
A 同源站 slug（含跨商家）+ C 已合并 + B 标题相似（只 high）；Q8 的价差 >3x 族不建。

写库口径：
- ``VariantFamily`` 全量重建（派生数据，先删后建，幂等）；
- ``VariantFamilyMember`` 一条 = (族, SPU, SKU, 该市场 ACTIVE Offer)，跨商族按
  商家/offer 展开；``is_representative`` 标在代表 SPU 的所有行上；
- 不动物流/评分/价格等业务数据；搜索文档回填由 ``backfill_family_search_fields`` 负责。
"""

import collections
import json
import os
from pathlib import Path

from catalog.models import Sku, Spu, VariantFamily, VariantFamilyMember
from catalog.variant_family_services import hidden_card_stats, plan_families
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from offers.models import Market, Offer


def _axis_label(specification) -> str:
    """SKU 规格 → 展示串（``Size: 140g`` / ``Colour: Black; Size: M``）。"""

    if not isinstance(specification, dict) or not specification:
        return ""
    parts = []
    for key, value in specification.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value)
        parts.append(f"{key}: {value}")
    return "; ".join(parts)[:160]


class Command(BaseCommand):
    help = "建同款族（VariantFamily / VariantFamilyMember），默认 DRY_RUN。"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="真正写库（默认只打印）")
        parser.add_argument("--market", default="GB", help="成员 offer 取哪个市场（默认 GB）")
        parser.add_argument("--locale", default="en-GB", help="标题/规格本地化（默认 en-GB）")
        parser.add_argument(
            "--report",
            default=str(
                Path(settings.REPOSITORY_ROOT)
                / "var"
                / "variant_family_db_20261127"
                / "build_report.json"
            ),
            help="写库台账 JSON 路径（默认 var/variant_family_db_20261127/build_report.json）",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        market_code = options["market"]
        locale_code = options["locale"]
        market = Market.objects.get(code=market_code)

        plan = plan_families(market_code=market_code, locale_code=locale_code)
        stats = dict(plan.stats)
        hidden = hidden_card_stats(plan, market_code=market_code, locale_code=locale_code)
        stats["hidden_docs"] = hidden["hidden_docs"]
        stats["hidden_docs_by_kind"] = hidden["by_kind"]

        self.stdout.write(
            "plan: families={families} by_kind={by_kind} members={members} "
            "excluded_price_spread={excluded_price_spread} title_listed={title_listed} "
            "hidden_docs={hidden_docs}".format(**stats)
        )

        report = {
            "generated_at": timezone.now().isoformat(),
            "applied": apply,
            "market": market_code,
            "locale": locale_code,
            "stats": stats,
            "excluded_price_spread": plan.excluded_price_spread,
            "families": [],
        }

        if not apply:
            report["families"] = [
                {
                    "family_key": row["family_key"],
                    "kind": row["kind"],
                    "representative_public_id": str(
                        Spu.objects.only("public_id").get(pk=row["representative_pk"]).public_id
                    ),
                    "member_count": row["member_count"],
                }
                for row in plan.families
            ]
            self._write_report(options["report"], report)
            self.stdout.write(self.style.WARNING("DRY_RUN：未写库。加 --apply 才落库。"))
            return

        # 成员展开：每个成员 SPU 的 ACTIVE SKU × 该市场 ACTIVE Offer。
        sku_rows = collections.defaultdict(list)  # spu_id -> [(sku, axis_label)]
        for sku in (
            Sku.objects.filter(spu_id__in={pk for f in plan.families for pk in f["member_pks"]})
            .filter(status=Sku.Status.ACTIVE)
            .only("pk", "spu_id", "specification")
            .order_by("pk")
        ):
            sku_rows[sku.spu_id].append((sku, _axis_label(sku.specification)))

        offer_rows = collections.defaultdict(list)  # sku_id -> [(offer, merchant_label)]
        for offer in (
            Offer.objects.filter(
                market=market,
                status=Offer.Status.ACTIVE,
                sku__status=Sku.Status.ACTIVE,
                sku__spu__status=Spu.Status.ACTIVE,
            )
            .select_related("merchant")
            .order_by("pk")
        ):
            offer_rows[offer.sku_id].append((offer, offer.merchant.display_name[:160]))

        created_families = 0
        created_members = 0
        families_without_members = []
        with transaction.atomic():
            VariantFamily.objects.all().delete()
            for order, row in enumerate(plan.families):
                representative_pk = row["representative_pk"]
                family = VariantFamily.objects.create(
                    family_key=row["family_key"],
                    kind=row["kind"],
                    representative_spu_id=representative_pk,
                    confidence=row["confidence"],
                    axis_hint=row["axis_hint"][:64],
                    evidence=row["evidence"][:240],
                    member_count=row["member_count"],
                )
                created_families += 1
                member_sort = 0
                member_rows = []
                for spu_id in row["member_pks"]:
                    is_rep = spu_id == representative_pk
                    for sku, axis in sku_rows.get(spu_id, []):
                        offers = offer_rows.get(sku.pk, [])
                        if not offers:
                            member_rows.append(
                                VariantFamilyMember(
                                    family=family,
                                    spu_id=spu_id,
                                    sku=sku,
                                    offer=None,
                                    axis_label=axis,
                                    merchant_label="",
                                    is_representative=is_rep,
                                    sort_order=member_sort,
                                )
                            )
                            member_sort += 1
                            continue
                        for offer, merchant_label in offers:
                            member_rows.append(
                                VariantFamilyMember(
                                    family=family,
                                    spu_id=spu_id,
                                    sku=sku,
                                    offer=offer,
                                    axis_label=axis,
                                    merchant_label=merchant_label,
                                    is_representative=is_rep,
                                    sort_order=member_sort,
                                )
                            )
                            member_sort += 1
                VariantFamilyMember.objects.bulk_create(member_rows, batch_size=500)
                created_members += len(member_rows)
                if not member_rows:
                    families_without_members.append(row["family_key"])
                if created_families % 200 == 0:
                    self.stdout.write(
                        f"  ... {created_families} families / {created_members} members"
                    )

        report["applied_at"] = timezone.now().isoformat()
        report["created_families"] = created_families
        report["created_members"] = created_members
        report["families_without_members"] = families_without_members
        report["families"] = [
            {
                "family_key": row["family_key"],
                "kind": row["kind"],
                "representative_public_id": str(
                    Spu.objects.only("public_id").get(pk=row["representative_pk"]).public_id
                ),
                "member_count": row["member_count"],
            }
            for row in plan.families
        ]
        self._write_report(options["report"], report)
        self.stdout.write(
            self.style.SUCCESS(
                f"apply: families={created_families} members={created_members} "
                f"without_members={len(families_without_members)}"
            )
        )
        self.stdout.write(f"report: {options['report']}")

    def _write_report(self, path, payload):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
