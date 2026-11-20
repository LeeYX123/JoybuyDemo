from django.http import JsonResponse

from catalog.models import CategoryMapping, LocalCategory, ProductSearchDocument
from catalog.search_services import (
    SearchParamsInvalid,
    recommendation_documents,
    search_documents,
)
from offers.market_services import offer_market_chain, resolve_market_context

PAGE_SIZE = 24

# 顶部导航（一级品类行 + Categories 下拉面板）不展示的一级品类。
# 只影响导航入口：品类树 / 频道页直链（/minihome/<code>）/ 列表页
# （/c/<slug>）与商品全部保留可用。列表放后端常量，前端不硬编码 slug。
NAV_HIDDEN_ROOT_SLUGS = frozenset({"computers-accessories", "clothing-accessories"})


def root_channel_codes() -> dict:
    """depth=0 本地一级 → 频道 code（CategoryMapping 反查 ``minihome:<code>``）。

    一级 ↔ 频道不是一一对应：家居生活同时挂着 Home-Living / Joymart /
    World-Foods 三个频道，电子产品挂着 Electronics / TV。一个一级对多个
    频道时取 source_id 排序（casefold）最小的频道——当前数据下正好是各
    一级的主频道（Home-Living < Joymart < World-Foods、Beauty <
    Everyday-Essentials、Electronics < TV）。没有 ``minihome:`` 映射的
    一级（computers-accessories、outdoor-sports）不在返回值里，前端按
    约定降级跳 ``/c/<slug>``。
    """

    grouped: dict[int, list[str]] = {}
    mappings = CategoryMapping.objects.filter(
        source_category__source_id__startswith="minihome:",
        local_category__depth=0,
    ).select_related("source_category")
    for mapping in mappings:
        code = mapping.source_category.source_id.removeprefix("minihome:")
        grouped.setdefault(mapping.local_category_id, []).append(code)
    return {
        local_category_id: sorted(codes, key=str.casefold)[0]
        for local_category_id, codes in grouped.items()
    }


def serialize_category(category: LocalCategory, locale=None) -> dict:
    localized_name = category.name
    if locale is not None:
        translation = next(
            (item for item in category.translations.all() if item.locale_id == locale.pk),
            None,
        )
        if translation:
            localized_name = translation.name
        elif locale.language_code == "en" and category.name_en:
            localized_name = category.name_en
        elif locale.language_code == "zh" and category.name_zh:
            localized_name = category.name_zh
    return {
        "public_id": str(category.public_id),
        "name": localized_name,
        "name_en": category.name_en,
        "name_zh": category.name_zh,
        "slug": category.slug,
        "depth": category.depth,
    }


def category_tree(request):
    """ACTIVE local navigation tree: roots with their direct children.

    The Categories panel (docs/12 §2) needs parent -> child linkage, so the
    nesting is done server-side; each root only carries one child level. The
    standard category order (docs/12 global convention #1) is ``sort_order``.
    """

    context = resolve_market_context(request)
    locale = context.locale if context else None
    roots = (
        LocalCategory.objects.filter(status=LocalCategory.Status.ACTIVE, parent__isnull=True)
        .prefetch_related("translations__locale")
        .order_by("sort_order", "path", "pk")
    )
    children = (
        LocalCategory.objects.filter(status=LocalCategory.Status.ACTIVE, parent__isnull=False)
        .prefetch_related("translations__locale")
        .order_by("sort_order", "path", "pk")
    )
    children_by_parent = {}
    for item in children:
        children_by_parent.setdefault(item.parent_id, []).append(item)
    channel_codes = root_channel_codes()
    payload = []
    for root in roots:
        data = serialize_category(root, locale)
        # 频道落地页（/minihome/<code>）入口：只有 depth=0 行带 code。
        data["channel_code"] = channel_codes.get(root.pk)
        # 顶部导航/下拉面板可见性（见 NAV_HIDDEN_ROOT_SLUGS）。
        data["visible_in_nav"] = root.slug not in NAV_HIDDEN_ROOT_SLUGS
        data["children"] = [
            serialize_category(child, locale) for child in children_by_parent.get(root.pk, [])
        ]
        payload.append(data)
    return JsonResponse(
        {
            "market": context.market.code if context else None,
            "locale": locale.code if locale else None,
            "categories": payload,
        }
    )


def _resolve_search_market(context):
    """按 offer 市场链挑出第一个有可搜索文档的 (market, locale_code)。

    storefront_search / recommendations 共用的兜底逻辑：请求市场+locale 没有
    文档时，沿市场链回退（含回退市场的默认 locale）。
    """

    market = context.market
    locale_code = context.locale.code
    for candidate_market in offer_market_chain(market):
        candidates = [(candidate_market, locale_code)]
        if candidate_market.default_locale != locale_code:
            candidates.append((candidate_market, candidate_market.default_locale))
        for candidate_market_item, candidate_locale in candidates:
            if ProductSearchDocument.objects.filter(
                market=candidate_market_item,
                locale_code=candidate_locale,
                is_searchable=True,
            ).exists():
                return candidate_market_item, candidate_locale
    return market, locale_code


def storefront_search(request):
    """Search and filter search documents; query params drive everything."""

    context = resolve_market_context(request)
    if context is None:
        return JsonResponse(
            {
                "error": {"code": "MARKET_UNAVAILABLE", "message": "Market not configured."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )

    market = context.market
    locale_code = context.locale.code
    search_market, search_locale_code = _resolve_search_market(context)

    category = None
    category_slug = request.GET.get("category", "").strip()
    if category_slug:
        category = LocalCategory.objects.filter(
            slug=category_slug, status=LocalCategory.Status.ACTIVE
        ).first()
        if category is None:
            return JsonResponse(
                {
                    "error": {"code": "CATEGORY_NOT_FOUND", "message": "Unknown category."},
                    "request_id": getattr(request, "request_id", None),
                },
                status=404,
            )

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    try:
        result = search_documents(
            market=search_market,
            locale_code=search_locale_code,
            query=request.GET.get("q", ""),
            category=category,
            brand=request.GET.get("brand", ""),
            min_price=request.GET.get("min_price"),
            max_price=request.GET.get("max_price"),
            sort=request.GET.get("sort", "relevance"),
            page=page,
        )
    except SearchParamsInvalid as exc:
        return JsonResponse(
            {
                "error": {"code": "SEARCH_PARAMS_INVALID", "message": str(exc)},
                "request_id": getattr(request, "request_id", None),
            },
            status=400,
        )
    result["requested_market"] = market.code
    result["requested_locale"] = locale_code
    result["price_source_market"] = search_market.code
    result["display_currency_symbol"] = market.display_currency_symbol
    return JsonResponse(result)


def recommendations(request):
    """首页【为您推荐】：全站 ACTIVE 商品确定性混排，24 件/页（需求文档03 11.6）。

    频道页【精选好物】扩展（需求文档03 13.4）：可选 ``category=<slug>`` 只取该
    类目子树商品；``cycle=1`` 页号超池后取模循环。响应结构不变。
    """

    context = resolve_market_context(request)
    if context is None:
        return JsonResponse(
            {
                "error": {"code": "MARKET_UNAVAILABLE", "message": "Market not configured."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1

    category = None
    category_slug = request.GET.get("category", "").strip()
    if category_slug:
        category = LocalCategory.objects.filter(
            slug=category_slug, status=LocalCategory.Status.ACTIVE
        ).first()
        if category is None:
            return JsonResponse(
                {
                    "error": {"code": "CATEGORY_NOT_FOUND", "message": "Unknown category."},
                    "request_id": getattr(request, "request_id", None),
                },
                status=404,
            )

    cycle = request.GET.get("cycle", "").strip() == "1"
    try:
        search_market, search_locale_code = _resolve_search_market(context)
        result = recommendation_documents(
            market=search_market,
            locale_code=search_locale_code,
            page=page,
            category=category,
            cycle=cycle,
        )
    except SearchParamsInvalid as exc:
        return JsonResponse(
            {
                "error": {"code": "SEARCH_PARAMS_INVALID", "message": str(exc)},
                "request_id": getattr(request, "request_id", None),
            },
            status=400,
        )
    if request.GET.get("has_local_image") == "1":
        result["items"] = _filter_local_images(result.get("items") or [])
        result["total"] = len(result["items"])
    result["requested_market"] = context.market.code
    result["requested_locale"] = context.locale.code
    result["price_source_market"] = search_market.code
    result["display_currency_symbol"] = context.market.display_currency_symbol
    return JsonResponse(result)


def _filter_local_images(items: list[dict]) -> list[dict]:
    """Drop items whose local ``/media/`` file is missing (批次 O 14.2).

    Some crawled products kept a DB row but their downloaded image file is
    absent; the activity landing page must not render broken images. This is
    opt-in via ``has_local_image=1`` so other callers keep the full pool.
    """

    from pathlib import Path

    from django.conf import settings

    root = Path(settings.MEDIA_ROOT)
    prefix = "/media/"
    filtered = []
    for item in items:
        path = str(item.get("image_path") or "")
        if path.startswith(prefix) and not (root / path[len(prefix) :]).is_file():
            continue
        filtered.append(item)
    return filtered
