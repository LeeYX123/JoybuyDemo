"""同款多规格 SPU 合并（批次 CB2，2026-11-27）。

把「同一源站 slug 家族、标题只差规格后缀」的多个 SPU 合并为一个保留 SPU +
多个规格 SKU。默认 DRY_RUN（只打印/写计划 CSV），``--apply`` 才写库。

口径（用户 2026-11-27 拍板）：
- A 类（同 slug + 归一化标题相同）批量合并；跨商家组绝对不合并；
- B2 类（同 slug、标题被改写）先抽样校验，通过后按批合并；
- 保留 SPU = 组内**最早创建且 ACTIVE + 有 ACTIVE Offer** 的一个；
- 不物理删除：被合并 SPU 归档（INACTIVE）+ 写 ``SpuAlias``（旧 URL 301）。

单组失败不影响其它组；每组一个事务，全量状态写进 ``--backup`` JSON，
``var/variant_merge_20261126/rollback_merge.py`` 按它逆序恢复。
"""

import csv
import difflib
import itertools
import json
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, OperationalError, ProgrammingError, connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

WORKSPACE = Path(__file__).resolve().parents[4] / "var" / "variant_merge_20261126"

MAX_LABEL_LEN = 70
MIN_PREFIX_COVERAGE = 0.5
# B2 标题被改写过，「公共前缀」常常只剩品牌+商品名，后缀是较长的规格描述
# （``Media Console Grey Gold Fluted 100cm``）。公共前缀覆盖率放宽到 0.35，
# 由「共享图 / 标题相似度」这道证据闸门兜底。
B2_MIN_PREFIX_COVERAGE = 0.35
B2_MIN_TITLE_SIMILARITY = 0.75
MAX_PRICE_RATIO = Decimal("3")

COLOUR_WORDS = frozenset(
    """
    black white red blue green yellow purple pink orange grey gray brown beige cream
    ivory silver gold bronze rose navy teal turquoise violet magenta maroon khaki
    clear transparent multicolour multicolor charcoal slate taupe lilac lavender
    peach mint coral burgundy wine olive tan camel chocolate light dark pale deep
    bright natural rustic oak walnut pine ash marl
    """.split()
)
SIZE_ONLY_RE = re.compile(
    r"^\d+(?:[.,]\d+)?\s?(?:g|gr|grams?|kg|ml|l|cl|oz|lb|lbs|cm|mm|m|inch|in|ft|pcs?"
    r"|pieces?|count|ct|tablets?|capsules?|caps|sachets?|servings?|pack|packs)$",
    re.IGNORECASE,
)
PACK_RE = re.compile(r"\b\d+\s*(?:pack|packs|pcs|pieces|count|ct|x)\b", re.IGNORECASE)

# 标题尾部「商品类型/营销填充词」：不是规格，剥掉才能得到干净变体标签。
# 例：``300g Food Supplement`` → ``300g``（用户给的胶原蛋白组）。
FILLER_TAILS = ("food supplements", "food supplement", "supplement", "style")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def common_word_prefix(titles: list[str]) -> list[str]:
    """组内标题的**词级**公共前缀（字符级前缀会切在词中间，产生 ``edia`` 这类残词）。"""

    token_lists = [title.split() for title in titles]
    prefix: list[str] = []
    for column in zip(*token_lists):
        if len(column) != len(token_lists):  # 组内最短标题已用完
            break
        if all(token.casefold() == column[0].casefold() for token in column):
            prefix.append(column[0])
        else:
            break
    return prefix


def strip_common_tail(labels: list[str]) -> list[str]:
    """去掉所有标签共有的尾部词（如 ``300g Food Supplement`` → ``300g``）。"""

    token_lists = [label.split() for label in labels]
    shared = 0
    while True:
        if any(len(tokens) <= shared + 1 for tokens in token_lists):
            break
        tails = [tokens[len(tokens) - 1 - shared].casefold() for tokens in token_lists]
        if all(tail == tails[0] for tail in tails):
            shared += 1
        else:
            break
    if not shared:
        return labels
    return [" ".join(tokens[: len(tokens) - shared]) for tokens in token_lists]


def clean_label(label: str) -> str:
    return normalize_space(re.sub(r"^[\s\-–—|,;:+&/()\[\]]+|[\s\-–—|,;:()\[\]]+$", "", label))


def strip_filler(label: str) -> str:
    """剥掉标签尾部的商品类型/营销填充词（保留至少一个词）。"""

    changed = True
    while changed:
        changed = False
        folded = label.casefold()
        for tail in FILLER_TAILS:
            if folded == tail:
                break
            if folded.endswith(" " + tail):
                label = clean_label(label[: len(label) - len(tail) - 1])
                changed = True
                break
    return label


def derive_labels(
    titles: list[str], *, min_coverage: float = MIN_PREFIX_COVERAGE
) -> tuple[str, list[str] | None, str]:
    """返回 ``(base_title, labels|None, reason)``；labels 为 None 时 reason 说明原因。"""

    titles = [normalize_space(title) for title in titles]
    if any(not title for title in titles):
        return "", None, "blank_title"
    prefix = common_word_prefix(titles)
    base = clean_label(" ".join(prefix))
    median_len = sorted(len(title) for title in titles)[len(titles) // 2]
    if len(base) < min_coverage * max(median_len, 1):
        return base, None, "prefix_too_short"
    labels = [clean_label(" ".join(title.split()[len(prefix) :])) for title in titles]
    if all(labels):
        stripped = [clean_label(label) for label in strip_common_tail(labels)]
        # 公共尾部若是规格单位（``4 x 2.5kg Bags`` 的 ``x 2.5kg Bags``），剥完只剩
        # 数字（``4`` / ``2``），用户看不出含义 —— 这种组保留剥前的完整后缀。
        if all(any(ch.isalpha() for ch in label) for label in stripped):
            labels = stripped
        labels = [strip_filler(label) for label in labels]
    if any(not label for label in labels):
        return base, None, "empty_label"
    folded = [label.casefold() for label in labels]
    if len(set(folded)) != len(folded):
        return base, None, "duplicate_label"
    if any(len(label) > MAX_LABEL_LEN for label in labels):
        return base, None, "label_too_long"
    return base, labels, ""


def detect_axis(labels: list[str]) -> str:
    folded = [label.casefold() for label in labels]
    # 字母尺码（S/M/L/XL/XXL…）也是 Size 轴，单独列白名单避免误判。
    letter_sizes = {"xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl"}
    if all(label in letter_sizes for label in folded):
        return "Size"
    if all(
        len(label) <= 24
        and any(re.search(rf"\b{re.escape(word)}\b", label) for word in COLOUR_WORDS)
        for label in folded
    ):
        return "Colour"
    if all(len(label) <= 16 and SIZE_ONLY_RE.match(label) for label in folded):
        return "Size"
    if all(len(label) <= 24 and PACK_RE.search(label) for label in folded):
        return "Pack"
    return "Style"


def title_similarity(titles: list[str]) -> float:
    """组内标题两两相似度最小值（B2 抽样校验用，报数不参与硬判定）。"""

    if len(titles) < 2:
        return 1.0
    ratios = [
        difflib.SequenceMatcher(
            None, normalize_space(a).casefold(), normalize_space(b).casefold()
        ).ratio()
        for a, b in itertools.combinations(titles, 2)
    ]
    return round(min(ratios), 3)


@dataclass
class Member:
    spu: object
    public_id: str
    title: str
    created_at: object
    status: str
    is_activity: bool
    skus: list = field(default_factory=list)
    merchant_ids: set = field(default_factory=set)
    prices: list = field(default_factory=list)
    gallery_shas: set = field(default_factory=set)
    orders_n: int = 0
    reviews_n: int = 0
    docs_n: int = 0
    has_alias: bool = False


@dataclass
class Plan:
    group_id: str
    tier: str
    members: list[Member]
    status: str = "ok"
    reason: str = ""
    keep: Member | None = None
    merged: list[Member] = field(default_factory=list)
    base_title: str = ""
    labels: dict = field(default_factory=dict)
    axis: str = ""
    price_ratio: object = None
    shared_images: int = 0
    title_similarity: float = 1.0
    already_merged: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Command(BaseCommand):
    help = "同款多规格 SPU 合并（批次 CB2）：默认 DRY_RUN，--apply 才写库。"

    def add_arguments(self, parser):
        parser.add_argument("--candidates", required=True, help="候选 CSV 路径")
        parser.add_argument("--tier", required=True, choices=["A", "B2"])
        parser.add_argument("--plan", default="", help="DRY_RUN 计划 CSV 输出路径")
        parser.add_argument("--apply", action="store_true", help="实际写库（默认只演练）")
        parser.add_argument("--backup", default=str(WORKSPACE / "backup_merge.json"))
        parser.add_argument("--result", default=str(WORKSPACE / "result.csv"))
        parser.add_argument("--skip", default=str(WORKSPACE / "skip_underivable.csv"))
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个可合并组")
        parser.add_argument(
            "--offset", type=int, default=0, help="跳过前 N 个可合并组（分批执行用）"
        )
        parser.add_argument(
            "--group-id", action="append", default=[], help="只处理指定组（可重复）"
        )
        parser.add_argument(
            "--force-group-id",
            action="append",
            default=[],
            help=(
                "人工确认过的组：仅豁免 csv_not_auto_merge_ok 与 price_spread_gt3x "
                "两道闸门（如用户给的胶原蛋白 140g/300g/600g 价差 3.07x），"
                "其余校验（同商家/无订单/无评价/单 SKU/标签可派生）照常执行"
            ),
        )

    # ------------------------------------------------------------------ 入口
    def handle(self, *args, **options):
        self.tier = options["tier"]
        self.forced = set(options["force_group_id"])
        rows = self._load_rows(options["candidates"], self.tier)
        if options["group_id"]:
            wanted = set(options["group_id"])
            rows = [row for row in rows if row["group_id"] in wanted]
        if not rows:
            raise CommandError("没有匹配的候选组。")

        plans = [self._build_plan(row) for row in rows]
        ok_plans = [plan for plan in plans if plan.ok]
        offset = options["offset"] or 0
        if offset or options["limit"]:
            selected = (
                ok_plans[offset:]
                if not options["limit"]
                else ok_plans[offset : offset + options["limit"]]
            )
            allowed = {plan.group_id for plan in selected}
            ok_plans = [plan for plan in ok_plans if plan.group_id in allowed]
            plans = [
                plan
                if not plan.ok or plan.group_id in allowed
                else replace(plan, status="skipped", reason="limit")
                for plan in plans
            ]

        if options["plan"]:
            self._write_plan_csv(Path(options["plan"]), plans)

        self._print_summary(plans, ok_plans)
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY_RUN：未写库。确认计划后加 --apply 执行。"))
            return

        backup_path = Path(options["backup"])
        result_path = Path(options["result"])
        if not ok_plans:
            self.stdout.write(self.style.WARNING("没有可执行的组。"))
            return
        self._apply(ok_plans, backup_path, result_path, options["batch_size"])

    # -------------------------------------------------------------- 候选读取
    def _load_rows(self, path: str, tier: str) -> list[dict]:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if row.get("class") == tier]
        if not rows:
            raise CommandError(f"{path} 里没有 class={tier} 的候选组。")
        return rows

    # ------------------------------------------------------------ 计划与校验
    def _build_plan(self, row: dict) -> Plan:
        from django.contrib.contenttypes.models import ContentType

        from catalog.models import ProductSearchDocument, Spu, SpuAlias
        from media.models import MediaUsage
        from offers.models import Offer
        from orders.models import OrderItem
        from reviews.models import Review

        # A 类只执行分类阶段判定为可自动合并的组（同商家 / 标签可派生 / 无订单 /
        # 无多 SKU 成员 / 价差 ≤3x）。这里不是信任 CSV，而是**收窄**范围：
        # 之后仍会逐组按库内实时状态重新校验。人工确认的组（--force-group-id）
        # 只豁免这一道与价差闸门。
        forced = row["group_id"] in getattr(self, "forced", set())
        if self.tier == "A" and row.get("auto_merge_ok") != "yes" and not forced:
            return Plan(
                group_id=row["group_id"],
                tier=self.tier,
                members=[],
                status="skipped",
                reason="csv_not_auto_merge_ok",
            )

        public_ids = [row["keep_spu_public_id"]] + [
            item for item in row["merge_spu_public_ids"].split(";") if item
        ]
        public_ids = list(dict.fromkeys(public_ids))
        spus = {
            str(spu.public_id): spu
            for spu in Spu.objects.filter(public_id__in=public_ids).select_related(
                "brand", "local_category"
            )
        }
        missing = [item for item in public_ids if item not in spus]
        if missing:
            return Plan(
                group_id=row["group_id"],
                tier=self.tier,
                members=[],
                status="skipped",
                reason="missing_spu:" + ",".join(missing[:3]),
            )

        spu_ct = ContentType.objects.get_for_model(Spu)
        titles = self._titles(list(spus.values()))
        members = []
        for public_id in public_ids:
            spu = spus[public_id]
            skus = list(spu.skus.all().order_by("pk"))
            offers = list(Offer.objects.filter(sku__spu=spu).select_related("currency"))
            active_prices = [
                offer.current_price for offer in offers if offer.status == Offer.Status.ACTIVE
            ]
            gallery = set(
                MediaUsage.objects.filter(
                    content_type=spu_ct, object_id=spu.pk, role="gallery"
                ).values_list("asset__sha256", flat=True)
            )
            members.append(
                Member(
                    spu=spu,
                    public_id=public_id,
                    title=titles.get(public_id, ""),
                    created_at=spu.created_at,
                    status=spu.status,
                    is_activity=spu.is_activity,
                    skus=skus,
                    merchant_ids={offer.merchant_id for offer in offers},
                    prices=active_prices,
                    gallery_shas=gallery,
                    orders_n=OrderItem.objects.filter(spu_public_id=public_id).count(),
                    reviews_n=Review.objects.filter(spu=spu, status=Review.Status.ACTIVE).count(),
                    docs_n=ProductSearchDocument.objects.filter(spu=spu).count(),
                    has_alias=SpuAlias.objects.filter(old_public_id=spu.public_id).exists(),
                )
            )

        plan = Plan(group_id=row["group_id"], tier=self.tier, members=members)
        # 幂等：合并完成后组内恰好剩一个 ACTIVE（保留商品）、其余都已归档且
        # 带别名。重跑同一批候选时这些组直接跳过，不重复合并。
        active_members = [m for m in members if m.status == Spu.Status.ACTIVE]
        if (
            len(active_members) == 1
            and not active_members[0].has_alias
            and all(m.has_alias for m in members if m.status != Spu.Status.ACTIVE)
        ):
            plan.status = "skipped"
            plan.reason = "already_merged"
            plan.already_merged = True
            return plan

        reasons: list[str] = []
        if any(member.is_activity for member in members):
            reasons.append("is_activity")
        if any(len(member.skus) != 1 for member in members):
            reasons.append("multi_sku_member")
        if any(member.orders_n for member in members):
            reasons.append("has_orders")
        if any(member.reviews_n for member in members):
            reasons.append("has_reviews")
        merchants = set().union(*(member.merchant_ids for member in members))
        if len(merchants) != 1:
            reasons.append("mixed_merchant")

        sellable = [
            member for member in members if member.status == Spu.Status.ACTIVE and member.prices
        ]
        if not sellable:
            reasons.append("no_active_member")

        prices = [price for member in members for price in member.prices]
        if len({member.public_id for member in members if member.prices}) >= 2 and prices:
            plan.price_ratio = (max(prices) / min(prices)).quantize(Decimal("0.01"))
            if plan.price_ratio > MAX_PRICE_RATIO and not forced:
                reasons.append("price_spread_gt3x")

        base, labels, label_reason = derive_labels(
            [member.title for member in members],
            min_coverage=(MIN_PREFIX_COVERAGE if self.tier == "A" else B2_MIN_PREFIX_COVERAGE),
        )
        plan.base_title = base
        plan.title_similarity = title_similarity([member.title for member in members])
        if labels is None:
            reasons.append(f"label_{label_reason or 'underivable'}")
        else:
            plan.labels = dict(zip([member.public_id for member in members], labels))
            plan.axis = detect_axis(labels)
            # B2：标题被改写过，必须再有一层一致性证据（共享图 sha 或高标题相似度）。
            if self.tier == "B2":
                sets = [member.gallery_shas for member in members]
                if all(sets):
                    plan.shared_images = len(set.intersection(*sets))
                plan.shared_images = max(
                    plan.shared_images,
                    max(
                        (len(a & b) for a, b in itertools.combinations(sets, 2)),
                        default=0,
                    ),
                )
                if not plan.shared_images and plan.title_similarity < B2_MIN_TITLE_SIMILARITY:
                    reasons.append("b2_weak_evidence")

        if sellable:
            plan.keep = sorted(sellable, key=lambda m: (m.created_at, m.public_id))[0]
        elif members:
            plan.keep = sorted(members, key=lambda m: (m.created_at, m.public_id))[0]
        if plan.keep is not None:
            plan.merged = [m for m in members if m.public_id != plan.keep.public_id]

        if reasons:
            plan.status = "skipped"
            plan.reason = "|".join(reasons)
        return plan

    def _titles(self, spus) -> dict:
        from catalog.models import ProductSearchDocument, SpuTranslation

        ids = [spu.pk for spu in spus]
        titles = {}
        for spu_id, locale, title in SpuTranslation.objects.filter(spu_id__in=ids).values_list(
            "spu_id", "locale", "title"
        ):
            if locale == "en-GB" or spu_id not in titles:
                titles[spu_id] = title
        for spu_id, title in ProductSearchDocument.objects.filter(
            spu_id__in=ids, locale_code="en-GB"
        ).values_list("spu_id", "title"):
            titles.setdefault(spu_id, title)
        return {str(spu.public_id): titles.get(spu.pk, "") for spu in spus}

    # ----------------------------------------------------------------- 输出
    def _print_summary(self, plans: list[Plan], ok_plans: list[Plan]) -> None:
        skipped = [plan for plan in plans if not plan.ok and not plan.already_merged]
        already = [plan for plan in plans if plan.already_merged]
        reason_counts: dict[str, int] = {}
        for plan in skipped:
            for reason in plan.reason.split("|"):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        self.stdout.write(
            f"tier={self.tier} 组={len(plans)} 可合并={len(ok_plans)} "
            f"合并 SPU={sum(len(p.members) for p in ok_plans)} "
            f"将归档={sum(len(p.merged) for p in ok_plans)} "
            f"跳过={len(skipped)} 已合并={len(already)}"
        )
        for reason, count in sorted(reason_counts.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  跳过原因 {reason}: {count}")
        for plan in ok_plans[:10]:
            keep = plan.keep
            self.stdout.write(
                f"  {plan.group_id} keep={keep.public_id} n={len(plan.members)} "
                f"axis={plan.axis} labels={list(plan.labels.values())[:6]} "
                f"ratio={plan.price_ratio} shared_img={plan.shared_images} "
                f"orders={sum(m.orders_n for m in plan.members)} "
                f"reviews={sum(m.reviews_n for m in plan.members)}"
            )
        if len(ok_plans) > 10:
            self.stdout.write(f"  ... 共 {len(ok_plans)} 组")

    def _write_plan_csv(self, path: Path, plans: list[Plan]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "group_id",
            "tier",
            "status",
            "reason",
            "keep_public_id",
            "keep_spu_id",
            "csv_keep_public_id",
            "merged_public_ids",
            "member_count",
            "axis",
            "labels",
            "base_title",
            "price_ratio",
            "shared_images",
            "title_similarity",
            "orders_items",
            "reviews",
            "sku_counts",
            "merchant_ids",
        ]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for plan in plans:
                writer.writerow(
                    [
                        plan.group_id,
                        plan.tier,
                        plan.status,
                        plan.reason,
                        plan.keep.public_id if plan.keep else "",
                        plan.keep.spu.pk if plan.keep else "",
                        plan.members[0].public_id if plan.members else "",
                        ";".join(m.public_id for m in plan.merged),
                        len(plan.members),
                        plan.axis,
                        " | ".join(plan.labels.values()),
                        plan.base_title,
                        str(plan.price_ratio) if plan.price_ratio is not None else "",
                        plan.shared_images,
                        plan.title_similarity,
                        sum(m.orders_n for m in plan.members),
                        sum(m.reviews_n for m in plan.members),
                        ";".join(str(len(m.skus)) for m in plan.members),
                        ";".join(
                            str(mid)
                            for mid in sorted(set().union(*(m.merchant_ids for m in plan.members)))
                        ),
                    ]
                )
        self.stdout.write(f"计划已写入 {path}（{len(plans)} 行）")

    # ----------------------------------------------------------------- 执行
    def _apply(self, plans: list[Plan], backup_path: Path, result_path: Path, batch: int) -> None:
        backup = self._load_backup(backup_path)
        batch = max(1, batch)
        results: list[dict] = self._load_results(result_path)
        done = {row["group_id"] for row in results}
        total_batches = (len(plans) + batch - 1) // batch
        for index in range(total_batches):
            chunk = plans[index * batch : (index + 1) * batch]
            self.stdout.write(
                self.style.HTTP_INFO(f"== 批次 {index + 1}/{total_batches}（{len(chunk)} 组）")
            )
            for plan in chunk:
                if plan.group_id in done:
                    continue
                try:
                    entry = self._merge_one(plan)
                except Exception as exc:  # noqa: BLE001 - 单组失败不能中断整批
                    self.stderr.write(self.style.ERROR(f"[{plan.group_id}] 合并失败：{exc!r}"))
                    results.append(
                        {
                            "group_id": plan.group_id,
                            "tier": plan.tier,
                            "status": "failed",
                            "reason": repr(exc)[:200],
                            "keep_public_id": plan.keep.public_id if plan.keep else "",
                            "merged_count": len(plan.merged),
                            "labels": " | ".join(plan.labels.values()),
                        }
                    )
                    continue
                backup["groups"].append(entry)
                results.append(
                    {
                        "group_id": plan.group_id,
                        "tier": plan.tier,
                        "status": "merged",
                        "reason": "",
                        "keep_public_id": entry["keep_public_id"],
                        "merged_count": len(entry["merged"]),
                        "labels": entry["labels"],
                    }
                )
            self._save_backup(backup_path, backup)
            self._save_results(result_path, results)
            merged = sum(1 for row in results if row["status"] == "merged")
            failed = sum(1 for row in results if row["status"] == "failed")
            archived = sum(
                int(row["merged_count"] or 0) for row in results if row["status"] == "merged"
            )
            self.stdout.write(f"   累计 merged={merged} failed={failed} 归档={archived}")
        self._save_backup(backup_path, backup)
        self._save_results(result_path, results)
        self.stdout.write(self.style.SUCCESS(f"完成：{len(plans)} 组，详见 {result_path}"))

    def _merge_one(self, plan: Plan) -> dict:
        from django.contrib.contenttypes.models import ContentType

        from catalog.models import (
            ProductSearchDocument,
            Sku,
            SkuSourceIdentity,
            Spu,
            SpuAlias,
            SpuSourceIdentity,
        )
        from catalog.product_services import canonicalize_source_specification
        from catalog.search_services import refresh_spu_search_documents
        from content.models import ActivitySectionProduct, ChannelModuleProduct
        from media.models import MediaUsage

        keep = plan.keep
        merged = plan.merged
        axis = plan.axis
        labels = plan.labels
        spu_ct = ContentType.objects.get_for_model(Spu)
        entry = {
            "group_id": plan.group_id,
            "tier": plan.tier,
            "axis": axis,
            "base_title": plan.base_title,
            "labels": " | ".join(labels.values()),
            "keep_public_id": keep.public_id,
            "keep_spu_id": keep.spu.pk,
            "keep_title": keep.title,
            "keep_status": keep.status,
            "keep_detail_spec_options": None,
            "keep_translation_id": None,
            "keep_translation_title": None,
            "keep_published_at": None,
            "merged": [],
            "skus": [],
            "identities": [],
            "media_usages": [],
            "videos": [],
            "favourites": [],
            "recently_viewed": [],
            "channel_items": [],
            "activity_items": [],
            "aliases": [],
            "search_documents": [],
            "detail_translations": [],
        }

        keep_spu = Spu.objects.get(pk=keep.spu.pk)
        with transaction.atomic():
            # 1) SKU：全部（含保留 SPU 自己的）写派生规格；被合并的改挂 keep。
            sku_source_ids: dict[int, list[str]] = {}
            for member in plan.members:
                label = labels[member.public_id]
                for sku in member.skus:
                    entry["skus"].append(
                        {
                            "public_id": str(sku.public_id),
                            "spu_public_id": str(member.spu.public_id),
                            "specification": sku.specification,
                            "specification_signature": sku.specification_signature,
                            "specification_merge_managed": sku.specification_merge_managed,
                        }
                    )
                    normalized, signature = canonicalize_source_specification({axis: label})
                    attempt = 1
                    while (
                        Sku.objects.filter(spu=keep_spu, specification_signature=signature)
                        .exclude(pk=sku.pk)
                        .exists()
                    ):
                        attempt += 1
                        if attempt > 9:
                            raise CommandError(
                                f"SKU 规格签名冲突无法消歧：{sku.public_id} {axis}={label}"
                            )
                        normalized, signature = canonicalize_source_specification(
                            {axis: f"{label} ({attempt})"}
                        )
                    sku.spu = keep_spu
                    sku.specification = normalized
                    sku.specification_signature = signature
                    sku.specification_merge_managed = True
                    sku.save(
                        update_fields=[
                            "spu",
                            "specification",
                            "specification_signature",
                            "specification_merge_managed",
                            "updated_at",
                        ]
                    )
                    sku_source_ids[sku.pk] = list(
                        SkuSourceIdentity.objects.filter(sku=sku).values_list(
                            "source_id", flat=True
                        )
                    )

            # 2) 源身份改挂（额外效果：爬虫下次抓到该变体页会命中 keep，不再建新 SPU）
            for member in merged:
                for identity in SpuSourceIdentity.objects.filter(spu=member.spu):
                    entry["identities"].append(
                        {"id": identity.pk, "spu_public_id": str(member.spu.public_id)}
                    )
                    identity.spu = keep_spu
                    identity.save(update_fields=["spu", "updated_at"])

            # 3) 保留 SPU 标题收敛为公共前缀（列表卡/PDP 不再显示某一个规格名）
            translation = keep_spu.translations.filter(locale="en-GB").first()
            if translation is not None and plan.base_title:
                entry["keep_translation_id"] = translation.pk
                entry["keep_translation_title"] = translation.title
                translation.title = plan.base_title[:500]
                translation.save(update_fields=["title", "updated_at"])

            # 4) 画廊 / 视频：改挂 keep 并按 asset 去重（unique 约束不允许重复）
            existing_media = {
                (usage.asset_id, usage.role)
                for usage in MediaUsage.objects.filter(content_type=spu_ct, object_id=keep_spu.pk)
            }
            next_order = (
                MediaUsage.objects.filter(content_type=spu_ct, object_id=keep_spu.pk)
                .order_by("-sort_order")
                .values_list("sort_order", flat=True)
                .first()
                or 0
            )
            for member in merged:
                for usage in MediaUsage.objects.filter(
                    content_type=spu_ct, object_id=member.spu.pk
                ).order_by("sort_order", "pk"):
                    entry["media_usages"].append(
                        {
                            "id": usage.pk,
                            "asset_id": usage.asset_id,
                            "content_type_id": usage.content_type_id,
                            "object_id": usage.object_id,
                            "role": usage.role,
                            "sort_order": usage.sort_order,
                            "created_at": usage.created_at.isoformat(),
                            "deleted_duplicate": False,
                        }
                    )
                    key = (usage.asset_id, usage.role)
                    if key in existing_media:
                        entry["media_usages"][-1]["deleted_duplicate"] = True
                        usage.delete()
                        continue
                    existing_media.add(key)
                    next_order += 1
                    usage.object_id = keep_spu.pk
                    usage.sort_order = next_order
                    usage.save(update_fields=["object_id", "sort_order"])

            from catalog.models import SpuVideo

            existing_videos = set(
                SpuVideo.objects.filter(spu=keep_spu).values_list("video_id", "poster_id")
            )
            for member in merged:
                for video in SpuVideo.objects.filter(spu=member.spu):
                    entry["videos"].append(
                        {
                            "id": video.pk,
                            "spu_public_id": str(member.spu.public_id),
                            "video_id": video.video_id,
                            "poster_id": video.poster_id,
                            "sort_order": video.sort_order,
                            "deleted_duplicate": False,
                        }
                    )
                    key = (video.video_id, video.poster_id)
                    if key in existing_videos:
                        entry["videos"][-1]["deleted_duplicate"] = True
                        video.delete()
                        continue
                    existing_videos.add(key)
                    video.spu = keep_spu
                    video.save(update_fields=["spu"])

            # 5) 买家收藏 / 足迹：改挂 keep，重复的按 unique 约束去重
            from accounts_buyers.models import Favourite, RecentlyViewed

            for member in merged:
                for favourite in Favourite.objects.filter(spu=member.spu):
                    duplicate = Favourite.objects.filter(
                        account_id=favourite.account_id, spu=keep_spu
                    ).exists()
                    entry["favourites"].append(
                        {
                            "id": favourite.pk,
                            "account_id": favourite.account_id,
                            "spu_public_id": str(member.spu.public_id),
                            "created_at": favourite.created_at.isoformat(),
                            "deleted_duplicate": duplicate,
                        }
                    )
                    if duplicate:
                        favourite.delete()
                    else:
                        favourite.spu = keep_spu
                        favourite.save(update_fields=["spu"])
                for recent in RecentlyViewed.objects.filter(spu=member.spu):
                    existing = RecentlyViewed.objects.filter(
                        account_id=recent.account_id, spu=keep_spu
                    ).first()
                    entry["recently_viewed"].append(
                        {
                            "id": recent.pk,
                            "account_id": recent.account_id,
                            "spu_public_id": str(member.spu.public_id),
                            "viewed_at": recent.viewed_at.isoformat(),
                            "deleted_duplicate": bool(existing),
                        }
                    )
                    if existing is not None:
                        recent.delete()
                    else:
                        recent.spu = keep_spu
                        recent.save(update_fields=["spu"])

            # 6) 内容位引用改挂 keep（活动/频道按 SKU 出卡的设计不变）。唯一键
            #    (module/section, spu, sku) 可能撞既有位次：撞了保持原样并记录。
            for member in merged:
                for item in ChannelModuleProduct.objects.filter(spu=member.spu):
                    entry["channel_items"].append(
                        {"id": item.pk, "spu_public_id": str(member.spu.public_id)}
                    )
                    try:
                        with transaction.atomic():
                            item.spu = keep_spu
                            item.save(update_fields=["spu"])
                    except IntegrityError:
                        entry["channel_items"][-1]["conflict"] = True
                for item in ActivitySectionProduct.objects.filter(spu=member.spu):
                    entry["activity_items"].append(
                        {"id": item.pk, "spu_public_id": str(member.spu.public_id)}
                    )
                    try:
                        with transaction.atomic():
                            item.spu = keep_spu
                            item.save(update_fields=["spu"])
                    except IntegrityError:
                        entry["activity_items"][-1]["conflict"] = True

            # 7) keep 的 SpuDetail.spec_options 换成派生轴（PDP 规格按钮首选它）
            detail = getattr(keep_spu, "detail", None)
            if detail is not None:
                entry["keep_detail_spec_options"] = detail.spec_options
                values = []
                for sku in Sku.objects.filter(spu=keep_spu).order_by("pk"):
                    label = sku.specification.get(axis, "")
                    values.append(
                        {
                            "value": label,
                            "image_url": "",
                            "sku_ids": sku_source_ids.get(sku.pk, []),
                        }
                    )
                detail.spec_options = [{"name": axis, "values": values}]
                detail.save(update_fields=["spec_options", "updated_at"])

            # 8) 详情译文行（translation_agent 维护，Django 不管）：清 spec_options
            #    让请求语言回退到 detail.spec_options；原值进备份。
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, spec_options FROM spu_detail_translation WHERE spu_id = %s",
                        [keep_spu.pk],
                    )
                    for row in cursor.fetchall():
                        entry["detail_translations"].append({"id": row[0], "spec_options": row[1]})
                    if entry["detail_translations"]:
                        cursor.execute(
                            "UPDATE spu_detail_translation SET spec_options = NULL "
                            "WHERE spu_id = %s",
                            [keep_spu.pk],
                        )
            except (OperationalError, ProgrammingError):
                # 测试库/未初始化环境没有这张表：跳过即可。
                entry["detail_translations"] = []

            # 9) 搜索文档：备份 keep 的发布时间（重建会刷成 now）
            keep_doc = ProductSearchDocument.objects.filter(spu=keep_spu).first()
            if keep_doc is not None and keep_doc.published_at:
                entry["keep_published_at"] = keep_doc.published_at.isoformat()

            # 10) 归档被合并 SPU + 写别名 + 删其搜索文档
            for member in merged:
                for doc in ProductSearchDocument.objects.filter(spu=member.spu):
                    entry["search_documents"].append(
                        {
                            "id": doc.pk,
                            "spu_public_id": str(member.spu.public_id),
                            "market_id": doc.market_id,
                            "locale_code": doc.locale_code,
                            "title": doc.title,
                            "brand_name": doc.brand_name,
                            "local_category_id": doc.local_category_id,
                            "min_price": str(doc.min_price) if doc.min_price is not None else None,
                            "max_price": str(doc.max_price) if doc.max_price is not None else None,
                            "currency_code": doc.currency_code,
                            "rating_average": (
                                str(doc.rating_average) if doc.rating_average is not None else None
                            ),
                            "rating_count": doc.rating_count,
                            "is_searchable": doc.is_searchable,
                            "published_at": (
                                doc.published_at.isoformat() if doc.published_at else None
                            ),
                        }
                    )
                    doc.delete()
                Spu.objects.filter(pk=member.spu.pk).update(status=Spu.Status.INACTIVE)
                alias = SpuAlias.objects.create(
                    old_public_id=member.spu.public_id,
                    spu=keep_spu,
                    reason=f"CB2/{plan.tier}/{plan.group_id}"[:120],
                )
                entry["aliases"].append(
                    {"id": alias.pk, "old_public_id": str(member.spu.public_id)}
                )
                entry["merged"].append(
                    {
                        "public_id": str(member.spu.public_id),
                        "spu_id": member.spu.pk,
                        "status": member.status,
                    }
                )

            # 11) 重建 keep 搜索文档（价格区间、卡片数），并恢复原发布时间
            refresh_spu_search_documents(keep_spu)
            published = [
                doc["published_at"] for doc in entry["search_documents"] if doc["published_at"]
            ]
            if entry["keep_published_at"]:
                published.append(entry["keep_published_at"])
            if published:
                earliest = min(
                    (parse_datetime(value) for value in published),
                    key=lambda value: value or timezone.now(),
                )
                if earliest is not None:
                    ProductSearchDocument.objects.filter(spu=keep_spu).update(published_at=earliest)

            expected_skus = sum(len(member.skus) for member in plan.members)
            actual_skus = Sku.objects.filter(spu=keep_spu).count()
            if actual_skus != expected_skus:
                raise CommandError(f"SKU 数校验失败：期望 {expected_skus}，实际 {actual_skus}")

        entry["merged_at"] = timezone.now().isoformat()
        return entry

    # ----------------------------------------------------------------- 台账
    def _load_backup(self, path: Path) -> dict:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("groups"), list):
                    return payload
            except (json.JSONDecodeError, OSError):
                self.stderr.write(self.style.WARNING(f"备份文件无法解析，将覆盖：{path}"))
        return {"created_at": timezone.now().isoformat(), "groups": []}

    def _save_backup(self, path: Path, backup: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup["updated_at"] = timezone.now().isoformat()
        path.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding="utf-8")

    def _save_results(self, path: Path, results: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "group_id",
            "tier",
            "status",
            "reason",
            "keep_public_id",
            "merged_count",
            "labels",
        ]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(results)

    def _load_results(self, path: Path) -> list[dict]:
        """跨批次累积台账：A 类跑完再跑 B2 时不覆盖前面的行。"""

        if not path.exists():
            return []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return [row for row in csv.DictReader(handle)]
