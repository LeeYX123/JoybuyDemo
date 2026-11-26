"""批次 DB：回填 ``ProductSearchDocument`` 的三个族字段（默认 DRY_RUN）。

用法::

    .venv/Scripts/python.exe backend/manage.py backfill_family_search_fields           # 只统计
    .venv/Scripts/python.exe backend/manage.py backfill_family_search_fields --apply   # 写库

口径（与 ``catalog/variant_family_services.family_fields_for_spu`` 一致）：

- ``family_key``：该 SPU 所属族的族键；不在族里 = 空串；
- ``is_family_representative``：是否族代表（列表/搜索只出代表卡）；不在族里 = True；
- ``family_max_price``：族内各 SPU 在该市场「最低可购价」的最大值；不在族里 = NULL。

必须**先** ``build_variant_families --apply``，且回滚时要把它一起清掉
（``var/variant_family_db_20261127/rollback_variant_families.py``）。
"""

import json
import os
from pathlib import Path

from catalog.models import ProductSearchDocument, VariantFamilyMember
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Min
from django.utils import timezone
from offers.models import Offer


class Command(BaseCommand):
    help = "回填搜索文档的 family_key / is_family_representative / family_max_price。"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="真正写库（默认只统计）")
        parser.add_argument(
            "--report",
            default=str(
                Path(settings.REPOSITORY_ROOT)
                / "var"
                / "variant_family_db_20261127"
                / "search_backfill_report.json"
            ),
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        membership = {}
        for spu_id, family_key, rep_id, family_id in VariantFamilyMember.objects.values_list(
            "spu_id", "family__family_key", "family__representative_spu_id", "family_id"
        ):
            membership[spu_id] = (family_key, rep_id, family_id)

        family_members = {}
        for family_id, spu_id in VariantFamilyMember.objects.values_list("family_id", "spu_id"):
            family_members.setdefault(family_id, set()).add(spu_id)

        # (market_id, family_id) → 族内最高价
        family_max_price = {}
        for market_id, market_code in Offer.objects.values_list(
            "market_id", "market__code"
        ).distinct():
            per_spu = (
                Offer.objects.filter(market_id=market_id, status=Offer.Status.ACTIVE)
                .values("sku__spu_id")
                .annotate(low=Min("current_price"))
            )
            spu_low = {row["sku__spu_id"]: row["low"] for row in per_spu if row["low"] is not None}
            for family_id, spu_ids in family_members.items():
                prices = [spu_low[spu_id] for spu_id in spu_ids if spu_id in spu_low]
                if prices:
                    family_max_price[(market_id, family_id)] = max(prices)

        docs = list(
            ProductSearchDocument.objects.values(
                "pk",
                "spu_id",
                "market_id",
                "family_key",
                "is_family_representative",
                "family_max_price",
            )
        )
        now = timezone.now()
        updated = 0
        changed_rows = []
        stats = {
            "docs": len(docs),
            "in_family": 0,
            "representatives": 0,
            "non_representatives": 0,
            "with_family_max_price": 0,
            "need_update": 0,
        }
        for doc in docs:
            membership_row = membership.get(doc["spu_id"])
            if membership_row is None:
                new_key, new_rep, new_max = "", True, None
            else:
                family_key, rep_id, family_id = membership_row
                new_key = family_key
                new_rep = rep_id == doc["spu_id"]
                new_max = family_max_price.get((doc["market_id"], family_id))
                stats["in_family"] += 1
                if new_rep:
                    stats["representatives"] += 1
                else:
                    stats["non_representatives"] += 1
                if new_max is not None:
                    stats["with_family_max_price"] += 1
            if (
                doc["family_key"] != new_key
                or doc["is_family_representative"] != new_rep
                or doc["family_max_price"] != new_max
            ):
                stats["need_update"] += 1
                changed_rows.append(
                    ProductSearchDocument(
                        pk=doc["pk"],
                        family_key=new_key,
                        is_family_representative=new_rep,
                        family_max_price=new_max,
                        updated_at=now,
                    )
                )

        result = {"applied": apply, "generated_at": timezone.now().isoformat(), **stats}
        if apply and changed_rows:
            with transaction.atomic():
                ProductSearchDocument.objects.bulk_update(
                    changed_rows,
                    ["family_key", "is_family_representative", "family_max_price", "updated_at"],
                    batch_size=1000,
                )
                updated = len(changed_rows)
        result["updated"] = updated

        os.makedirs(os.path.dirname(options["report"]), exist_ok=True)
        with open(options["report"], "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=1)
        self.stdout.write(json.dumps(result, ensure_ascii=False))
        if not apply:
            self.stdout.write(self.style.WARNING("DRY_RUN：未写库。加 --apply 才落库。"))
