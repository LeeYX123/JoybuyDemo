"""Storefront search and category listing (WP-22).

Reads only the flattened ``ProductSearchDocument`` table so every list
query is fully indexed (docs/03 §5). Text search uses MySQL FULLTEXT with
a fallback to prefix LIKE for short queries; sorting and pagination are
stable (price/rating tiebreak on spu id) and depth-capped.
"""

import hashlib
import re
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import ProductSearchDocument

SORT_CHOICES = (
    "relevance",
    "price_asc",
    "price_desc",
    "rating_desc",
    "newest",
)

MAX_PAGE = 50
PAGE_SIZE = 24

# 首页【为您推荐】池上限（需求文档03 11.6：10 页 × 24 = 240 件）。
RECOMMENDATION_POOL_SIZE = 240
RECOMMENDATION_PAGE_SIZE = 24

# InnoDB FULLTEXT 的最小索引词长（innodb_ft_min_token_size，默认 3）。
# 比它短的词（如「17」「4L」）在 BOOLEAN MODE 里带 + 号会让整条 MATCH 命中 0，
# 所以这些词走 LIKE 兜底，其余词仍用全文索引。
MIN_FULLTEXT_TOKEN = 3


def _search_terms(text: str) -> list[str]:
    """把用户输入拆成安全的检索词：去掉 BOOLEAN MODE 运算符，避免语法/语义注入。"""

    return [term for term in re.sub(r'[+\-<>()~*"@]', " ", text or "").split() if term]


def _term_filter(terms: list[str]) -> Q:
    """逐词 LIKE（AND）：标题或品牌包含每个词。用于短词与全文检索的兜底。"""

    combined = Q()
    for term in terms:
        combined &= Q(title__icontains=term) | Q(brand_name__icontains=term)
    return combined


class SearchParamsInvalid(Exception):
    pass


def _parse_decimal(value):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def refresh_spu_search_documents(spu) -> int:
    """平台下架/单 Offer 下架后即时刷新一个 SPU 的全部搜索文档（迭代02）。

    - SPU 非 ACTIVE 或没有任何 ACTIVE Offer → 删除该 SPU 全部文档（搜索立刻搜不到）；
    - 否则按现有口径重建每个有 ACTIVE Offer 的市场文档。
    返回删除的文档数（重建返回 0，方便调用方记日志）。
    """

    from offers.models import Market, Offer

    from catalog.models import Spu

    has_active_offer = Offer.objects.filter(
        sku__spu=spu, status=Offer.Status.ACTIVE
    ).exists()
    if spu.status != Spu.Status.ACTIVE or not has_active_offer:
        deleted, _ = ProductSearchDocument.objects.filter(spu=spu).delete()
        return deleted
    markets = Market.objects.filter(
        pk__in=Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE).values_list(
            "market_id", flat=True
        )
    )
    for market in markets:
        rebuild_search_document(spu, market=market)
    return 0


def rebuild_search_documents(*, market, locale_code: str | None = None, full: bool = True) -> int:
    """Rebuild search documents for one market from live catalog data.

    Full rebuild: refresh every SPU with an ACTIVE offer. Returns the
    number of documents written. Incremental per-SPU refresh is done by
    ``rebuild_search_document(spu, market)`` called by import flows.
    """

    from offers.models import Offer

    from catalog.models import Spu

    del full
    spu_ids = set(
        Offer.objects.filter(
            market=market, status=Offer.Status.ACTIVE, sku__spu__status=Spu.Status.ACTIVE
        ).values_list("sku__spu_id", flat=True)
    )
    for spu in Spu.objects.filter(pk__in=spu_ids):
        rebuild_search_document(spu, market=market, locale_code=locale_code)
    return len(spu_ids)


def rebuild_search_document(
    spu,
    *,
    market,
    locale_code: str | None = None,
) -> ProductSearchDocument:
    """Refresh the search document of one SPU from its ACTIVE offers."""

    from django.db.models import Avg, Count
    from offers.models import Locale, Offer
    from reviews.models import Review

    from catalog.localization_services import resolve_product_content
    from catalog.models import Spu

    active_offers = list(
        Offer.objects.filter(
            sku__spu=spu, market=market, status=Offer.Status.ACTIVE
        ).select_related("currency")
    )
    locale_code = locale_code or market.default_locale
    locale = Locale.objects.filter(code=locale_code, is_active=True).first()
    if locale is None:
        raise ValueError(f"Unknown or inactive locale: {locale_code}")
    content = resolve_product_content(spu, market, locale)
    review_stats = Review.objects.filter(spu=spu, status=Review.Status.ACTIVE).aggregate(
        average=Avg("rating"), count=Count("pk")
    )
    rating_average = review_stats["average"]
    rating_count = review_stats["count"] or 0
    # 评分回退：本地没有 ACTIVE 评价时用源站快照（SpuDetail.rating_*），与
    # catalog/detail_views.py 的 review_summary 同口径（2026-11-23）。
    if not rating_count:
        detail = getattr(spu, "detail", None)
        if detail is not None and detail.rating_count:
            rating_average = detail.rating_average
            rating_count = detail.rating_count
    has_offer = bool(active_offers)
    prices = [offer.current_price for offer in active_offers] or [None]
    # 批次 DB：族去重字段随文档一起刷新（否则爬虫重导会把代表标记/族键冲掉）。
    from catalog.variant_family_services import family_fields_for_spu

    family_fields = family_fields_for_spu(spu.pk, market)
    document, _ = ProductSearchDocument.objects.update_or_create(
        spu=spu,
        market=market,
        locale_code=locale.code,
        defaults={
            "title": content.title[:500],
            "brand_name": spu.brand.name if spu.brand else "",
            "local_category": spu.local_category,
            "min_price": min(prices),
            "max_price": max(prices),
            "currency_code": active_offers[0].currency.code if active_offers else "",
            "rating_average": rating_average,
            "rating_count": rating_count,
            "is_searchable": has_offer and spu.status == Spu.Status.ACTIVE,
            "family_key": family_fields["family_key"],
            "is_family_representative": family_fields["is_family_representative"],
            "family_max_price": family_fields["family_max_price"],
            "published_at": timezone.now() if has_offer else None,
        },
    )
    return document


def search_documents(
    *,
    market,
    locale_code: str | None = None,
    query: str = "",
    category=None,
    brand: str = "",
    min_price=None,
    max_price=None,
    sort: str = "relevance",
    page: int = 1,
) -> dict:
    """Query search documents; returns a serializable result envelope."""

    if sort not in SORT_CHOICES:
        raise SearchParamsInvalid(f"Unknown sort: {sort}.")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise SearchParamsInvalid("page must be a positive integer.")
    page = min(page, MAX_PAGE)

    locale_code = locale_code or market.default_locale
    # 批次 DB：列表/搜索按同款族去重，只出代表卡（文档已过滤，total/分页自动是
    # 去重后的真实值，不需要窗口函数）。
    queryset = ProductSearchDocument.objects.filter(
        market=market,
        locale_code=locale_code,
        is_searchable=True,
        is_family_representative=True,
    ).select_related("spu", "spu__detail", "local_category")
    query = (query or "").strip()
    if query:
        cleaned = " ".join(query.split())[:100]
        terms = _search_terms(cleaned)
        from django.db import connection
        from django.db.models.expressions import RawSQL

        if connection.vendor == "mysql" and terms:
            # 短词（< innodb_ft_min_token_size）不能进 BOOLEAN MODE：带 + 号会让
            # 整条 MATCH 返回空（「iPhone 17」曾因此搜不到任何商品）。它们改用
            # LIKE；长词仍走全文索引，索引结果为空时再整体 LIKE 兜底。
            long_terms = [term for term in terms if len(term) >= MIN_FULLTEXT_TOKEN]
            like_filter = _term_filter(terms)
            if long_terms:
                boolean = " ".join(f"+{term}*" for term in long_terms)
                relevance = RawSQL(
                    "(MATCH(title) AGAINST (%s IN BOOLEAN MODE)"
                    " + MATCH(brand_name) AGAINST (%s IN BOOLEAN MODE))",
                    (boolean, boolean),
                )
                matched = queryset.alias(relevance=relevance).filter(relevance__gt=0)
                queryset = matched if matched.exists() else queryset.filter(like_filter)
            else:
                queryset = queryset.filter(like_filter)
        elif terms:
            # Non-MySQL backends (local SQLite checks) fall back to contains.
            queryset = queryset.filter(_term_filter(terms))
        else:
            # 输入只有运算符（如 "+"）：没有任何有效检索词，返回空结果而不是全部商品。
            queryset = queryset.none()
    if category is not None:
        from catalog.services import local_category_descendants

        category_ids = {
            category.pk,
            *local_category_descendants(category).values_list("pk", flat=True),
        }
        queryset = queryset.filter(local_category_id__in=category_ids)
    if brand.strip():
        queryset = queryset.filter(brand_name__iexact=brand.strip())
    parsed_min = _parse_decimal(min_price)
    parsed_max = _parse_decimal(max_price)
    if parsed_min is not None:
        queryset = queryset.filter(max_price__gte=parsed_min)
    if parsed_max is not None:
        queryset = queryset.filter(min_price__lte=parsed_max)

    # 价格排序口径与卡片价一致（Q4）：族内最高价优先，缺失回退 min_price。
    price_order = Coalesce("family_max_price", "min_price")
    orderings = {
        "relevance": ("title", "pk"),
        "price_asc": (price_order, "pk"),
        "price_desc": (price_order.desc(), "pk"),
        "rating_desc": ("-rating_average", "-rating_count", "pk"),
        "newest": ("-published_at", "-pk"),
    }
    queryset = queryset.order_by(*orderings[sort])

    total = queryset.count()
    offset = (page - 1) * PAGE_SIZE
    rows = list(queryset[offset : offset + PAGE_SIZE])
    image_paths = _first_gallery_images(rows)
    return {
        "market": market.code,
        "locale": locale_code,
        "display_currency_symbol": market.display_currency_symbol,
        "query": query,
        "page": page,
        "page_size": PAGE_SIZE,
        "total": total,
        "total_pages": (total + PAGE_SIZE - 1) // PAGE_SIZE,
        "sort": sort,
        "items": [
            serialize_search_row(row, image_path=image_paths.get(row.spu_id, "")) for row in rows
        ],
    }


def _first_gallery_images(rows: list[ProductSearchDocument]) -> dict[int, str]:
    """Resolve the first local gallery image for a search page in one query."""

    if not rows:
        return {}
    from django.contrib.contenttypes.models import ContentType
    from media.models import MediaUsage
    from media.storage import media_url

    from catalog.models import Spu

    spu_type = ContentType.objects.get_for_model(Spu)
    usages = (
        MediaUsage.objects.filter(
            content_type=spu_type,
            object_id__in={row.spu_id for row in rows},
            role="gallery",
        )
        .select_related("asset")
        .order_by("object_id", "sort_order", "pk")
    )
    result = {}
    for usage in usages:
        result.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return result


def retail_price_text(spu) -> str | None:
    """后台零售价（``Spu.retail_price``）的字符串口径：与 ``price_min`` 一致。

    ``str(Decimal)`` 保留字段的 4 位小数（``19.9900``），null 输出 null。
    ``serialize_search_row`` 只读已 ``select_related`` 的 ``row.spu``，不额外查库。
    """

    if spu is None or spu.retail_price is None:
        return None
    return str(spu.retail_price)


def serialize_search_row(row: ProductSearchDocument, *, image_path: str = "") -> dict:
    detail = None
    try:
        detail = row.spu.detail  # select_related("spu__detail") 时零额外查询
    except Exception:  # noqa: BLE001 - detail 缺失时 SpuDetail.DoesNotExist
        detail = None
    return {
        "spu_public_id": str(row.spu.public_id),
        "title": row.title,
        "brand": row.brand_name,
        "category_slug": row.local_category.slug if row.local_category else None,
        "price_min": str(row.min_price) if row.min_price is not None else None,
        "price_max": str(row.max_price) if row.max_price is not None else None,
        "retail_price": retail_price_text(row.spu),
        "currency": row.currency_code,
        "rating_average": str(row.rating_average) if row.rating_average is not None else None,
        "rating_count": row.rating_count,
        "sold_amount": (detail.sale_amount or None) if detail is not None else None,
        "image_path": image_path,
        # 批次 DB：族去重字段。卡片价格优先 ``family_max_price``（族内最高价），
        # 缺失（不在族里/无价）时前端回退 ``price_min``。
        "family_key": row.family_key,
        "is_family_representative": row.is_family_representative,
        "family_max_price": (
            str(row.family_max_price) if row.family_max_price is not None else None
        ),
    }


def recommendation_documents(
    *,
    market,
    locale_code: str | None = None,
    page: int = 1,
    category=None,
    cycle: bool = False,
) -> dict:
    """首页【为您推荐】池：全站 ACTIVE 商品跨品类混合，顺序确定性（需求文档03 11.6）。

    排序用 ``md5(spu_public_id)`` 十六进制串做稳定伪随机键——同一个商品每次请求
    都在同一个位置（刷新不乱序），又不像纯主键序那样一眼假。池子上限
    ``RECOMMENDATION_POOL_SIZE``（240 = 10 页 × 24），不足 240 时有多少给多少。

    频道页【精选好物】扩展（需求文档03 13.4）：

    * ``category`` 传入一级/二级 ``LocalCategory`` 时只取该类目子树的 ACTIVE 商品；
    * ``cycle=True`` 时页号超过池子总页数就取模循环（从头再来），响应结构不变，
      ``page`` 返回取模后的真实页号，``total``/``total_pages`` 仍是池子真实大小，
      前端据此自行判断「池子已耗尽、当前内容是循环批次」。
    """

    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise SearchParamsInvalid("page must be a positive integer.")

    locale_code = locale_code or market.default_locale
    # is_searchable 是 rebuild_search_document 写入的快照：商品导入/下架流程
    # 中 SPU 状态和 Offer 活性可能已经变化（并发爬虫导入时尤其如此），只信
    # 快照会让「精选好物/为您推荐」混入 PDP 已 404 的商品（验收 FAIL-A）。
    # 池子构建时对 SPU ACTIVE + 该市场 ACTIVE Offer 做实时校验。
    from django.db.models import Exists, OuterRef
    from offers.models import Offer

    from catalog.models import Spu

    active_offer = Offer.objects.filter(
        sku__spu=OuterRef("spu_id"),
        market=market,
        status=Offer.Status.ACTIVE,
    )
    base = ProductSearchDocument.objects.filter(
        market=market,
        locale_code=locale_code,
        is_searchable=True,
        is_family_representative=True,
        spu__status=Spu.Status.ACTIVE,
    ).annotate(has_active_offer=Exists(active_offer)).filter(has_active_offer=True)
    if category is not None:
        # 与 search_documents 同口径：类目 + 全部后代（树只有 depth 0/1）。
        from catalog.services import local_category_descendants

        category_ids = {
            category.pk,
            *local_category_descendants(category).values_list("pk", flat=True),
        }
        base = base.filter(local_category_id__in=category_ids)
    pool_rows = list(base.values_list("spu_id", "spu__public_id"))
    pool_rows.sort(key=lambda row: (hashlib.md5(str(row[1]).encode("utf-8")).hexdigest(), row[0]))
    pool_rows = pool_rows[:RECOMMENDATION_POOL_SIZE]

    total = len(pool_rows)
    total_pages = max((total + RECOMMENDATION_PAGE_SIZE - 1) // RECOMMENDATION_PAGE_SIZE, 1)
    if cycle and total > 0:
        # 池子耗尽后循环：页号取模回到第 1 页重新开始（13.4 第 4 步）。
        page = ((page - 1) % total_pages) + 1
    else:
        page = min(page, total_pages)
    offset = (page - 1) * RECOMMENDATION_PAGE_SIZE
    page_slice = pool_rows[offset : offset + RECOMMENDATION_PAGE_SIZE]

    order = {spu_id: index for index, (spu_id, _) in enumerate(page_slice)}
    rows = list(
        ProductSearchDocument.objects.filter(spu_id__in=order)
        .select_related("spu", "spu__detail", "local_category")
    )
    rows.sort(key=lambda row: order[row.spu_id])
    image_paths = _first_gallery_images(rows)
    return {
        "market": market.code,
        "locale": locale_code,
        "display_currency_symbol": market.display_currency_symbol,
        "page": page,
        "page_size": RECOMMENDATION_PAGE_SIZE,
        "total": total,
        "total_pages": total_pages,
        "items": [
            serialize_search_row(row, image_path=image_paths.get(row.spu_id, "")) for row in rows
        ],
    }
