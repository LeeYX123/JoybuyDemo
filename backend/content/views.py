from django.http import JsonResponse

from content.campaign_services import campaign_payload
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
