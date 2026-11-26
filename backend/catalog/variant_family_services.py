"""同款族（VariantFamily）的计算与落库规则（2026-11-27 批次 DB）。

设计原则：**族计算是纯函数**，``var/variant_family_db_20261127/build_preview.py``
（预览）与 ``catalog/management/commands/build_variant_families.py``（写库）
共用本模块，避免「预览一套规则、写库另一套」。

三类族（用户 2026-11-27 拍板 Q3/Q6/Q7/Q8）：

* **A 同源站 slug**：``SpuSourceIdentity(source_system="joybuy_uk")`` 的
  ``source_url`` 里 ``/dp/<slug>/<source_id>`` 的 slug 相同即同族。**含跨商家**
  （全站自营，商家只是同一商品的 Offer）。占位 slug ``x`` / ``-`` 不是族键。
* **B 标题相似**：同 ``local_category`` + 同商家 + 同品牌（都为空算同桶），
  ``sim = IDF 加权余弦``（标题 token，去掉含数字的 token）且满足：
  - ``sim >= 0.90`` 且（共享画廊 sha ≥1 **或** 价差 ≤3x）；或
  - ``sim >= 0.85`` 且（共享图 **或** 同非空品牌 **或** 词级公共前缀 ≥4）且 价差 ≤3x。
  只在不属于 A 族的在售 SPU 之间建族。
* **C 已合并**：``SpuAlias`` 的保留 SPU。若它与新出现的同 slug SPU 同族，并进
  那个 A 族并**强制当代表**（否则 PDP 的 ``?sku=`` 变体档案就丢了）。

**Q8**：族内价格跨度（各成员最低可购价 max/min）> 3x 的族**不建族**（保持多卡）。

代表选取：保留 SPU 优先 → 有可搜索文档 → 在售 → ACTIVE → 创建最早 → pk 最小。
"""

import collections
import hashlib
import math
import re
from difflib import SequenceMatcher

#: B 族相似度门槛（Q6：0.85 + 强身份，而不是任务书初稿的 0.90）。
TITLE_HIGH_SIM = 0.85
#: B 族候选对下限（只用于聚类，不直接决定置信度）。
TITLE_LIST_SIM = 0.70
#: 价差上限（Q6 / Q8）。
PRICE_RATIO_MAX = 3.0
#: B 族「同标题头」判定：词级公共前缀（忽略纯数字 token）至少这么多个。
TITLE_HEAD_TOKENS = 4
PLACEHOLDER_SLUGS = frozenset({"x", "-"})
SLUG_RE = re.compile(r"/dp/([^/?#]+)/")


def normalize_tokens(title: str) -> list[str]:
    """标题 → 小写 token（去掉含数字的 token，型号差异不压低相似度）。"""

    text = (title or "").lower().replace("–", "-").replace("‑", "-").replace("’", "'")
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return [token for token in text.split() if not any(ch.isdigit() for ch in token)]


def build_idf(counters) -> dict[str, float]:
    total = sum(1 for counter in counters if counter)
    df = collections.Counter()
    for counter in counters:
        if counter:
            df.update(counter.keys())
    return {word: math.log((total + 1) / (count + 0.5)) for word, count in df.items()}


def cosine(counter_a, counter_b, idf, default_idf) -> float:
    dot = 0.0
    for word, count_a in counter_a.items():
        count_b = counter_b.get(word)
        if count_b:
            weight = idf.get(word, default_idf)
            dot += count_a * count_b * weight * weight
    if not dot:
        return 0.0
    norm_a = math.sqrt(sum((c * idf.get(w, default_idf)) ** 2 for w, c in counter_a.items()))
    norm_b = math.sqrt(sum((c * idf.get(w, default_idf)) ** 2 for w, c in counter_b.items()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def common_prefix_len(tokens_a: list[str], tokens_b: list[str]) -> int:
    """两条标题的词级公共前缀长度（忽略纯数字 token）。"""

    length = 0
    for left, right in zip(tokens_a, tokens_b):
        if left != right:
            break
        if not left.isdigit():
            length += 1
    return length


def axis_hint(titles: list[str]) -> str:
    """轴名提示（机械规则，沿用批次 DA 的 ``extract_axis_signals``）。"""

    from catalog.management.commands.merge_variant_spus import common_word_prefix
    from catalog.variant_archive_services import extract_axis_signals

    titles = [title or "" for title in titles]
    if len(titles) < 2:
        return ""
    prefix = common_word_prefix(titles)
    labels = [" ".join(title.split()[len(prefix) :]).strip() for title in titles]
    signals = [extract_axis_signals(label or title) for label, title in zip(labels, titles)]
    numeric = [sig for sig in signals if sig["numbers"]]
    unit_sets = {tuple(sorted(set(sig["units"]))) for sig in numeric}
    if numeric and len(numeric) == len(signals) and len(unit_sets) == 1:
        units = sorted(unit_sets.pop())
        if units and all(unit in {"ml", "cl", "l"} for unit in units):
            return "Capacity"
        if units and all(unit in {"g", "kg", "mg", "oz", "lb", "lbs"} for unit in units):
            return "Weight"
        if units and all(unit in {"cm", "mm", "m", "in", "inch", "inches", "ft"} for unit in units):
            return "Length"
        return "Size"
    if all(sig["colours"] and not sig["other_words"] and not sig["numbers"] for sig in signals):
        return "Colour"
    if any(sig["size_words"] for sig in signals):
        return "Style"
    return "Model/Style"


def title_similarity_debug(title_a: str, title_b: str) -> dict:
    """审计用：两条标题的实测差异（不参与判定）。"""

    return {
        "char_ratio": SequenceMatcher(
            None, (title_a or "").lower(), (title_b or "").lower()
        ).ratio(),
        "tokens_a": len(normalize_tokens(title_a)),
        "tokens_b": len(normalize_tokens(title_b)),
        "common_head": common_prefix_len(normalize_tokens(title_a), normalize_tokens(title_b)),
    }


def representative_sort_key(spu, *, sellable, doc_spu_ids, keep_ids):
    """代表选取：保留 SPU → 有卡片 → 在售 → ACTIVE → 创建最早 → pk 最小。

    ``spu`` 是 ``Spu.objects.values(...)`` 的字典（带 ``pk``/``status``/``created_at``）。
    """

    return (
        0 if spu["pk"] in keep_ids else 1,
        0 if spu["pk"] in doc_spu_ids else 1,
        0 if spu["pk"] in sellable else 1,
        0 if spu["status"] == "ACTIVE" else 1,
        spu["created_at"],
        spu["pk"],
    )


class FamilyPlan:
    """建族结果（不碰数据库写操作，只读快照 + 计算）。"""

    def __init__(self):
        self.families: list[dict] = []
        self.excluded_price_spread: list[dict] = []
        self.stats: dict = {}
        self.idf: dict[str, float] = {}
        self.tokens: dict[int, list[str]] = {}


def plan_families(*, market_code: str = "GB", locale_code: str = "en-GB", cap_title_families=False):
    """只读扫描全库，产出族计划（A/C/B + Q8 价差过滤）。

    返回 ``FamilyPlan``：
    - ``families``：每项 ``{family_key, kind, representative_pk, confidence, axis_hint,
      evidence, member_pks, member_count, notes}``；
    - ``excluded_price_spread``：Q8 被排除的族（保持多卡）；
    - ``stats``：计数（供命令/预览打印）。
    """

    from django.contrib.contenttypes.models import ContentType
    from media.models import MediaUsage
    from offers.models import Market, Offer

    from catalog.models import (
        ProductSearchDocument,
        Spu,
        SpuAlias,
        SpuSourceIdentity,
        SpuTranslation,
    )

    if cap_title_families:
        raise NotImplementedError("cap_title_families 未实现（预览/写库必须同规则）")

    market = Market.objects.get(code=market_code)
    spus = {
        row["pk"]: row
        for row in Spu.objects.values(
            "pk", "public_id", "status", "local_category_id", "brand_id", "created_at"
        )
    }
    titles = {}
    for spu_id, locale, title in SpuTranslation.objects.values_list("spu_id", "locale", "title"):
        if locale == locale_code:
            titles[spu_id] = title
        else:
            titles.setdefault(spu_id, title)

    merchants = collections.defaultdict(set)
    for merchant_id, spu_id in Offer.objects.filter(status=Offer.Status.ACTIVE).values_list(
        "merchant_id", "sku__spu_id"
    ):
        merchants[spu_id].add(merchant_id)

    prices = collections.defaultdict(list)
    for spu_id, price in Offer.objects.filter(
        market=market, status=Offer.Status.ACTIVE
    ).values_list("sku__spu_id", "current_price"):
        if price is not None:
            prices[spu_id].append(price)
    min_price = {spu_id: min(values) for spu_id, values in prices.items() if values}

    gallery_sha = collections.defaultdict(list)
    ct = ContentType.objects.get_for_model(Spu)
    for usage in (
        MediaUsage.objects.filter(content_type=ct, role="gallery")
        .select_related("asset")
        .order_by("object_id", "sort_order", "pk")
    ):
        gallery_sha[usage.object_id].append(usage.asset.sha256)

    doc_spu_ids = set(
        ProductSearchDocument.objects.filter(
            market=market, locale_code=locale_code, is_searchable=True
        ).values_list("spu_id", flat=True)
    )

    slug_by_spu = {}
    spus_by_slug = collections.defaultdict(set)
    for spu_id, source_url in SpuSourceIdentity.objects.filter(
        source_system="joybuy_uk"
    ).values_list("spu_id", "source_url"):
        match = SLUG_RE.search(source_url or "")
        if not match:
            continue
        slug = match.group(1)
        if slug in PLACEHOLDER_SLUGS:
            continue
        slug_by_spu.setdefault(spu_id, slug)
        spus_by_slug[slug].add(spu_id)

    keep_ids = {spu_id for spu_id in SpuAlias.objects.values_list("spu_id", flat=True) if spu_id}
    sellable = {
        spu_id for spu_id in min_price if spus.get(spu_id, {}).get("status") == Spu.Status.ACTIVE
    }

    def title_of(spu_id):
        if titles.get(spu_id):
            return titles[spu_id]
        return ""

    def sort_key(spu):
        return representative_sort_key(
            spu, sellable=sellable, doc_spu_ids=doc_spu_ids, keep_ids=keep_ids
        )

    plan = FamilyPlan()
    families = plan.families
    assigned = {}

    def price_spread(member_pks):
        values = [min_price[pk] for pk in member_pks if pk in min_price]
        if len(values) < 2 or not min(values):
            return None
        return float(max(values) / min(values))

    # ---- A 同 slug 族（含跨商家）------------------------------------------
    for slug, member_ids in sorted(spus_by_slug.items()):
        if len(member_ids) < 2:
            continue
        members = sorted((spus[pk] for pk in member_ids if pk in spus), key=sort_key)
        if not members:
            continue
        member_pks = [row["pk"] for row in members]
        spread = price_spread(member_pks)
        if spread is not None and spread > PRICE_RATIO_MAX:
            plan.excluded_price_spread.append(
                {
                    "family_key": f"slug:{slug}",
                    "kind": "slug",
                    "member_count": len(member_pks),
                    "price_spread": spread,
                }
            )
            continue
        families.append(
            {
                "family_key": f"slug:{slug}",
                "kind": "slug",
                "representative_pk": member_pks[0],
                "confidence": "high",
                "axis_hint": axis_hint([title_of(pk) for pk in member_pks]),
                "evidence": (
                    f"same_slug; members={len(member_pks)}; "
                    f"doc_members={sum(1 for pk in member_pks if pk in doc_spu_ids)}; "
                    f"merchants={len({m for pk in member_pks for m in merchants.get(pk, ())})}"
                ),
                "member_pks": member_pks,
                "member_count": len(member_pks),
            }
        )
        for pk in member_pks:
            assigned[pk] = f"slug:{slug}"

    # ---- C 已合并族（不在任何 A 族里的保留 SPU）--------------------------
    merged_only = 0
    merged_inside_slug = 0
    for keep_id in sorted(keep_ids):
        keep = spus.get(keep_id)
        if keep is None:
            continue
        if keep_id in assigned:
            merged_inside_slug += 1
            continue
        merged_only += 1
        families.append(
            {
                "family_key": f"merged:{keep['public_id']}",
                "kind": "merged",
                "representative_pk": keep_id,
                "confidence": "high",
                "axis_hint": "",
                "evidence": "merged_keep (CB2); members = SPU itself (multi SKU)",
                "member_pks": [keep_id],
                "member_count": 1,
            }
        )
        assigned[keep_id] = f"merged:{keep['public_id']}"

    # ---- B 标题相似族 -----------------------------------------------------
    token_lists = {spu_id: normalize_tokens(title_of(spu_id)) for spu_id in sellable}
    token_counters = {spu_id: collections.Counter(tokens) for spu_id, tokens in token_lists.items()}
    idf = build_idf(token_counters.values())
    plan.idf = idf
    plan.tokens = token_lists
    default_idf = math.log(len(token_counters) + 1)

    b_pool = [
        spu_id
        for spu_id in sellable
        if spu_id not in assigned and len(merchants.get(spu_id, ())) == 1
    ]
    buckets = collections.defaultdict(list)
    skipped_no_category = 0
    for spu_id in b_pool:
        if spus[spu_id]["local_category_id"] is None:
            skipped_no_category += 1
            continue
        buckets[
            (
                spus[spu_id]["local_category_id"],
                next(iter(merchants[spu_id])),
                spus[spu_id]["brand_id"],
            )
        ].append(spu_id)

    pair_candidates = 0
    pair_kept = 0
    pairs = []
    for ids in buckets.values():
        ids.sort(key=lambda spu_id: sort_key(spus[spu_id]))
        for index, left in enumerate(ids):
            counter_left = token_counters[left]
            if not counter_left:
                continue
            shas_left = set(gallery_sha.get(left, ()))
            for right in ids[index + 1 :]:
                counter_right = token_counters[right]
                if not counter_right:
                    continue
                pair_candidates += 1
                sim = cosine(counter_left, counter_right, idf, default_idf)
                if sim < TITLE_LIST_SIM:
                    continue
                shared = shas_left & set(gallery_sha.get(right, ()))
                ratio = _price_ratio(min_price, left, right)
                if not shared and not (ratio is not None and ratio <= PRICE_RATIO_MAX):
                    continue
                pair_kept += 1
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "sim": sim,
                        "shared_images": len(shared),
                        "price_ratio": ratio,
                        "same_brand": spus[left]["brand_id"] is not None,
                        "same_head": common_prefix_len(token_lists[left], token_lists[right])
                        >= TITLE_HEAD_TOKENS,
                    }
                )

    pairs.sort(key=lambda row: (-row["sim"], -row["shared_images"], row["left"], row["right"]))
    b_rep_of = {}
    b_members = collections.defaultdict(list)
    b_join = collections.defaultdict(dict)
    cross_family_pairs = 0
    for pair in pairs:
        left, right = pair["left"], pair["right"]
        left_rep, right_rep = b_rep_of.get(left), b_rep_of.get(right)
        if left_rep and right_rep:
            if left_rep != right_rep:
                cross_family_pairs += 1
            continue
        if not left_rep and not right_rep:
            rep = left if sort_key(spus[left]) <= sort_key(spus[right]) else right
            member = right if rep == left else left
            b_rep_of[rep] = rep
            b_rep_of[member] = rep
            b_members[rep] = [rep, member]
            b_join[rep][member] = pair
            continue
        rep = left_rep or right_rep
        member = right if left_rep else left
        if member in b_members[rep]:
            continue
        if cosine(token_counters[rep], token_counters[member], idf, default_idf) < TITLE_LIST_SIM:
            continue
        if pair["shared_images"] == 0:
            family_prices = [min_price[pk] for pk in b_members[rep] + [member] if pk in min_price]
            if (
                len(family_prices) >= 2
                and max(family_prices) / min(family_prices) > PRICE_RATIO_MAX
            ):
                continue
        b_members[rep].append(member)
        b_rep_of[member] = rep
        b_join[rep][member] = pair

    def pair_is_high(evidence) -> bool:
        shared = evidence["shared_images"] >= 1
        price_ok = (
            evidence["price_ratio"] is not None and evidence["price_ratio"] <= PRICE_RATIO_MAX
        )
        if evidence["sim"] >= 0.90:
            return shared or price_ok
        strong = shared or evidence["same_brand"] or evidence["same_head"]
        return evidence["sim"] >= TITLE_HIGH_SIM and strong and price_ok

    title_high = 0
    title_listed = 0
    listed_samples = []
    for rep in sorted(b_members):
        member_list = b_members[rep]
        evidence_pairs = [b_join[rep][member] for member in member_list if member != rep]
        min_sim = min(pair["sim"] for pair in evidence_pairs)
        max_shared = max(pair["shared_images"] for pair in evidence_pairs)
        ratios = [pair["price_ratio"] for pair in evidence_pairs if pair["price_ratio"] is not None]
        worst_ratio = max(ratios) if ratios else None
        member_list = sorted(member_list, key=lambda spu_id: sort_key(spus[spu_id]))
        rep = member_list[0]
        if all(pair_is_high(pair) for pair in evidence_pairs):
            confidence = "high"
            note = "all_joins:" + (
                "sim>=0.90&(img|price)"
                if min_sim >= 0.90
                else f"sim>={TITLE_HIGH_SIM}&(img|brand|head)&price"
            )
        elif min_sim >= TITLE_HIGH_SIM:
            confidence = "medium"
            note = "weak_identity"
        else:
            confidence = "low"
            note = "sim_in_[0.70,0.85)"
        digest = hashlib.sha1(
            f"{spus[rep]['local_category_id']}|{spus[rep]['brand_id']}|"
            f"{spus[rep]['public_id']}|{token_lists[rep]}".encode()
        ).hexdigest()[:12]
        family_key = f"title:{digest}"
        if confidence != "high":
            # Q6：只有 high 自动建族；med/low 只出清单（不落库）。
            title_listed += 1
            if len(listed_samples) < 200:
                listed_samples.append(
                    {
                        "family_key": family_key,
                        "kind": "title",
                        "confidence": confidence,
                        "member_count": len(member_list),
                        "representative_public_id": str(spus[rep]["public_id"]),
                        "representative_title": title_of(rep),
                        "similarity": round(min_sim, 4),
                        "member_titles": [title_of(pk) for pk in member_list],
                    }
                )
            continue
        spread = price_spread(member_list)
        if spread is not None and spread > PRICE_RATIO_MAX:
            plan.excluded_price_spread.append(
                {
                    "family_key": family_key,
                    "kind": "title",
                    "member_count": len(member_list),
                    "price_spread": spread,
                }
            )
            continue
        title_high += 1
        families.append(
            {
                "family_key": family_key,
                "kind": "title",
                "representative_pk": rep,
                "confidence": "high",
                "axis_hint": axis_hint([title_of(pk) for pk in member_list]),
                "evidence": (
                    f"{note}; min_sim={min_sim:.3f}; max_shared_img={max_shared}; "
                    f"worst_price_ratio={worst_ratio if worst_ratio is None else round(worst_ratio, 2)}"
                ),
                "member_pks": member_list,
                "member_count": len(member_list),
            }
        )
        for spu_id in member_list:
            assigned[spu_id] = family_key

    plan.stats = {
        "families": len(families),
        "by_kind": dict(collections.Counter(row["kind"] for row in families)),
        "members": sum(row["member_count"] for row in families),
        "excluded_price_spread": len(plan.excluded_price_spread),
        "title_high": title_high,
        "title_listed": title_listed,
        "merged_only": merged_only,
        "merged_inside_slug": merged_inside_slug,
        "pair_candidates": pair_candidates,
        "pair_kept": pair_kept,
        "cross_family_pairs": cross_family_pairs,
        "skipped_no_category": skipped_no_category,
        "searchable_docs": len(doc_spu_ids),
        "doc_spus_in_families": sum(1 for pk in doc_spu_ids if pk in assigned),
    }
    plan.listed_samples = listed_samples
    return plan


def _price_ratio(min_price, left, right):
    left_price, right_price = min_price.get(left), min_price.get(right)
    if not left_price or not right_price:
        return None
    return float(max(left_price, right_price) / min(left_price, right_price))


def family_fields_for_spu(spu_id: int, market) -> dict:
    """搜索文档的三个族字段（导入/刷新文档时实时算，避免爬虫把去重冲掉）。

    返回 ``{family_key, is_family_representative, family_max_price}``：
    - 不在任何族 → ``("", True, None)``（独立商品照常出卡）；
    - 族内最高价 = 族内各 SPU 在该市场「最低可购价」的最大值（与卡片口径一致）。
    """

    from django.db.models import Min
    from offers.models import Offer

    from catalog.models import VariantFamilyMember

    row = (
        VariantFamilyMember.objects.filter(spu_id=spu_id)
        .values("family_id", "family__family_key", "family__representative_spu_id")
        .first()
    )
    if row is None:
        return {"family_key": "", "is_family_representative": True, "family_max_price": None}
    member_spu_ids = list(
        VariantFamilyMember.objects.filter(family_id=row["family_id"]).values_list(
            "spu_id", flat=True
        )
    )
    per_spu = (
        Offer.objects.filter(
            market=market, status=Offer.Status.ACTIVE, sku__spu_id__in=set(member_spu_ids)
        )
        .values("sku__spu_id")
        .annotate(low=Min("current_price"))
    )
    prices = [item["low"] for item in per_spu if item["low"] is not None]
    return {
        "family_key": row["family__family_key"],
        "is_family_representative": row["family__representative_spu_id"] == spu_id,
        "family_max_price": max(prices) if prices else None,
    }


def hidden_card_stats(plan, *, market_code: str = "GB", locale_code: str = "en-GB") -> dict:
    """统计会隐藏多少张卡（按搜索文档），供预览/命令打印。"""

    from catalog.models import ProductSearchDocument

    hidden_docs = 0
    per_kind = collections.Counter()
    for family in plan.families:
        non_rep = family["member_pks"][1:]
        if not non_rep:
            continue
        count = ProductSearchDocument.objects.filter(
            market__code=market_code,
            locale_code=locale_code,
            is_searchable=True,
            spu_id__in=non_rep,
        ).count()
        hidden_docs += count
        per_kind[family["kind"]] += count
    return {"hidden_docs": hidden_docs, "by_kind": dict(per_kind)}
