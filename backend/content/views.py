from django.http import JsonResponse

from content.campaign_services import campaign_payload
from content.channel_banner_services import ChannelBannerError, public_banners
from content.services import get_published_page, serialize_page


def storefront_home(request):
    """Published home page modules for the SSR renderer (no auth, read-only).

    三个可运营模块——campaign_grid（活动卡片）、link_grid tiles（品类发现）
    与 weekly_picks（每周甄选）——各自用独立表数据覆盖快照里写死的对应
    模块；分区无卡片时保留快照，保证 CMS 未配置也能正常渲染。
    """

    page = get_published_page("home")
    if page is None:
        return JsonResponse(
            {
                "error": {"code": "CMS_PAGE_NOT_PUBLISHED", "message": "Home page not published."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )
    data = serialize_page(page)

    modules = list(data.get("modules") or [])
    injected = False
    for section, module_type in (
        ("campaign", "campaign_grid"),
        ("discovery", "link_grid"),
        ("weekly", "weekly_picks"),
    ):
        payload = campaign_payload(section)
        if payload is None:
            continue
        injected = True

        def owns_module(module: dict) -> bool:
            if module.get("type") != module_type:
                return False
            # link_grid 同时承载「品类发现」（tiles）与「心选品牌」
            # （brand_logos，静态快照模块，14.4 无需后台配置）；只覆盖前者，
            # 否则心选品牌会被品类发现的注入逻辑连带删除。
            if module_type == "link_grid":
                return (module.get("payload") or {}).get("variant") != "brand_logos"
            return True

        position = next(
            (m.get("position") for m in modules if owns_module(m)),
            None,
        )
        if position is None:
            if section == "weekly":
                # 14.2：【每周甄选】排在其后的楼层（真站顺序：品类发现 →
                # 心选品牌 → 每周甄选）之后。
                position = max((m.get("position") or 0 for m in modules), default=0) + 1
            else:
                position = 2
        modules = [m for m in modules if not owns_module(m)]
        modules.append({"position": position, "type": module_type, "payload": payload})
    if injected:
        modules.sort(key=lambda m: m.get("position") or 0)
        data["modules"] = modules
    return JsonResponse(data)


def channel_page_cards(request):
    """频道页品类卡下方的活动卡片（no auth, read-only，13.2）。

    契约：``GET /api/v1/cms/channel-page-cards?channel=<channel_code>``
    → ``{"items":[{id,image_url,link_url,sort_order}]}``（sort_order 升序，
    空配置或未知频道返回 ``{"items": []}``；``link_url`` 按 13.8 存原值）。
    缺少 ``channel`` 参数才报 400（调用方 bug，不是「没配置」）。
    """

    from content.channel_page_card_services import ChannelPageCardError, public_cards

    channel_code = str(request.GET.get("channel") or "").strip()
    try:
        rows = public_cards(channel_code)
    except ChannelPageCardError as exc:
        return JsonResponse(
            {
                "error": {"code": exc.code, "message": exc.message},
                "request_id": getattr(request, "request_id", None),
            },
            status=exc.status_code,
        )
    items = [
        {
            "id": str(row.public_id),
            "image_url": row.image_url,
            "link_url": row.link_url,
            "sort_order": row.sort_order,
        }
        for row in rows
    ]
    return JsonResponse({"channel": channel_code, "items": items, "total": len(items)})


def channel_banners(request):
    """频道页轮播图（no auth, read-only）：只返回该频道 enabled 的条目。

    未配置（或频道不存在）时返回空 ``items``，购物端据此回退渐变占位；
    缺少 ``channel_code`` 才报 400（调用方 bug，不是「没配置」）。
    """

    channel_code = str(request.GET.get("channel_code") or "").strip()
    try:
        rows = public_banners(channel_code)
    except ChannelBannerError as exc:
        return JsonResponse(
            {
                "error": {"code": exc.code, "message": exc.message},
                "request_id": getattr(request, "request_id", None),
            },
            status=exc.status_code,
        )
    items = [
        {
            "id": str(row.public_id),
            "image_url": row.image_url,
            "href": row.href,
            "sort_order": row.sort_order,
        }
        for row in rows
    ]
    return JsonResponse({"channel_code": channel_code, "items": items, "total": len(items)})


def channel_modules(request, code):
    """频道页商品楼层（no auth, read-only）：该类目特有的楼层 + 有序商品。

    未配置时返回空 ``modules``，购物端回退到通用商品楼层。
    """

    from content.channel_module_services import public_modules
    from offers.market_services import resolve_market_context

    context = resolve_market_context(request)
    if context is None:
        return JsonResponse(
            {
                "error": {"code": "MARKET_UNAVAILABLE", "message": "Market not configured."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )
    data = public_modules(
        code,
        market=context.market,
        locale_code=context.locale.code,
        language_code=context.locale.language_code,
    )
    data["market"] = context.market.code
    data["request_id"] = getattr(request, "request_id", None)
    return JsonResponse(data)
