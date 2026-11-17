from django.http import JsonResponse

from content.campaign_services import campaign_payload
from content.channel_banner_services import ChannelBannerError, public_banners
from content.services import get_published_page, serialize_page


def storefront_home(request):
    """Published home page modules for the SSR renderer (no auth, read-only).

    两个可运营模块——campaign_grid（活动卡片）与 link_grid tiles（品类发现）
    ——各自用独立表数据覆盖快照里写死的对应模块；分区无卡片时保留快照，
    保证 CMS 未配置也能正常渲染。
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
    ):
        payload = campaign_payload(section)
        if payload is None:
            continue
        injected = True
        position = next(
            (m.get("position") for m in modules if m.get("type") == module_type),
            None,
        )
        modules = [m for m in modules if m.get("type") != module_type]
        modules.append(
            {
                "position": position if position is not None else 2,
                "type": module_type,
                "payload": payload,
            }
        )
    if injected:
        modules.sort(key=lambda m: m.get("position") or 0)
        data["modules"] = modules
    return JsonResponse(data)


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
