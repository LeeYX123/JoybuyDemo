"""频道页（``/minihome/<code>``）品类卡下方的活动卡片：管理端 CRUD 与公开读取。

与 ``channel_banner_services`` 同一套纪律：独立模型（``ChannelPageCard``）
承接高频运营对象，不进 CMS 版本快照；``channel_code`` 只接受现有 minihome
频道，图片只接受本地 ``/media/`` 路径（禁止外链 CDN）。

跳转链接 ``link_url`` 按 13.8 链接规则**存原值、不限制、不改写**：管理端
保存什么就存什么（只去首尾空白），外链/站内路径的判定由购物端消费 helper
（``storefront/utils/cmsLink.js::resolveCmsLink()``，批次 I）负责。

``layout`` 是**组级**展示布局（`row2` / `row3` / `row3_scroll` / 历史值
`grid2x2`）：同一 ``(channel_code, group_index)`` 下所有卡片共用一个值。任何
写入传入 ``layout`` 时，服务层在同一事务里只把**该组**的卡片同步成同一个值，
不影响同频道的其它组。``channel_groups(code)`` 给出每组的概览
（``group_index`` / ``layout`` / ``count``），``channel_layout(code)`` 保持旧
语义（返回第一个组的布局）以兼容既有调用方。
"""

from django.db import transaction

from content.models import ActivityPage, ChannelCardSetting, ChannelPageCard

MAX_SORT_ORDER = 9999
MAX_GROUP_INDEX = 99

DEFAULT_LAYOUT = ChannelPageCard.Layout.ROW3
# 没有配置行的频道按这个默认值截断（母婴童玩用 max_cards=null 豁免）。
DEFAULT_CARD_LIMIT = 3


class ChannelPageCardError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _clean(value, *, field: str, max_length: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ChannelPageCardError("FIELD_REQUIRED", f"{field}不能为空。")
    if len(text) > max_length:
        raise ChannelPageCardError("FIELD_TOO_LONG", f"{field}不能超过 {max_length} 个字符。")
    return text


def channel_codes() -> set[str]:
    """现有 minihome 频道 code 集合（与频道页 banner 同源）。"""

    from content.channel_banner_services import channel_codes as _codes

    return _codes()


def validate_channel_code(value) -> str:
    code = _clean(value, field="频道", max_length=64, required=True)
    if code not in channel_codes():
        raise ChannelPageCardError("CHANNEL_CODE_INVALID", "频道不存在或不是可配置的一级频道。")
    return code


def validate_image_url(value) -> str:
    image = _clean(value, field="图片地址", max_length=1000, required=True)
    if not image.startswith("/media/") or any(ch.isspace() for ch in image):
        raise ChannelPageCardError(
            "IMAGE_URL_INVALID", "图片必须使用本站 /media/ 路径（不支持外部链接）。"
        )
    return image


def validate_link_url(value) -> str:
    """13.8：存原值不限制不改写（只去首尾空白、限长）。"""

    link = str(value or "").strip()
    if len(link) > 1000:
        raise ChannelPageCardError("FIELD_TOO_LONG", "跳转链接不能超过 1000 个字符。")
    return link


def validate_activity_page(value) -> ActivityPage | None:
    """绑定本地落地页：传活动页 public_id；空串/None 表示解除绑定。

    绑定后购物端跳转用 ``/active/<id>`` / ``/store/<id>``（页面 ID 与真站
    一致）；``link_url`` 保留原值仅作溯源。
    """

    raw = str(value or "").strip()
    if not raw:
        return None
    page = ActivityPage.objects.filter(public_id=raw).first()
    if page is None:
        raise ChannelPageCardError("ACTIVITY_PAGE_INVALID", "落地页不存在或已被删除。")
    return page


def channel_card_limit(channel_code: str) -> int | None:
    """购物端该频道的卡片上限；``None`` 表示不截断（频道级可配，ADR-0002）。"""

    setting = ChannelCardSetting.objects.filter(channel_code=channel_code).first()
    if setting is None:
        return DEFAULT_CARD_LIMIT
    return setting.max_cards


def validate_layout(value) -> str:
    """布局枚举校验：只接受 ``ChannelPageCard.Layout`` 的取值。

    ``grid2x2`` 只为兼容旧数据保留在 choices 里（新代码不再产生它）。
    """

    layout = str(value or "").strip()
    if layout not in ChannelPageCard.Layout.values:
        allowed = " / ".join(ChannelPageCard.Layout.values)
        raise ChannelPageCardError("LAYOUT_INVALID", f"布局只能是 {allowed}。")
    return layout


def validate_group_index(value) -> int:
    """组序号校验：同一频道内从 0 开始的非负整数。"""

    try:
        group_index = int(value)
    except (TypeError, ValueError):
        raise ChannelPageCardError("GROUP_INDEX_INVALID", "组序号必须是非负整数。") from None
    if group_index < 0 or group_index > MAX_GROUP_INDEX:
        raise ChannelPageCardError(
            "GROUP_INDEX_INVALID", f"组序号必须是 0–{MAX_GROUP_INDEX} 的整数。"
        )
    return group_index


def channel_layout(channel_code: str) -> str:
    """该频道第一个组当前生效的布局（向后兼容旧调用方）。

    频道还没有卡片时回落到默认 ``row3``。多组频道请改用
    :func:`channel_groups` 逐组读取布局。
    """

    layout = (
        ChannelPageCard.objects.filter(channel_code=channel_code)
        .order_by("group_index", "sort_order", "public_id")
        .values_list("layout", flat=True)
        .first()
    )
    return layout or DEFAULT_LAYOUT


def channel_groups(channel_code: str, *, active_only: bool = True) -> list[dict]:
    """该频道的组概览：``[{group_index, layout, count}]``，按组序号升序。

    ``active_only``（默认）只统计 ``is_active`` 的卡片，与公开接口口径一致；
    管理端要连下线行一起看时传 ``active_only=False``。
    """

    rows = ChannelPageCard.objects.filter(channel_code=channel_code)
    if active_only:
        rows = rows.filter(is_active=True)
    groups: dict[int, dict] = {}
    for group_index, layout in rows.order_by("group_index", "sort_order", "public_id").values_list(
        "group_index", "layout"
    ):
        group = groups.get(group_index)
        if group is None:
            groups[group_index] = {"group_index": group_index, "layout": layout, "count": 1}
        else:
            group["count"] += 1
    return [groups[key] for key in sorted(groups)]


def group_layout(channel_code: str, group_index: int) -> str:
    """指定组当前生效的布局；该组还没有卡片时回落到默认 ``row3``。"""

    layout = (
        ChannelPageCard.objects.filter(channel_code=channel_code, group_index=group_index)
        .order_by("sort_order", "public_id")
        .values_list("layout", flat=True)
        .first()
    )
    return layout or DEFAULT_LAYOUT


def _sync_group_layout(channel_code: str, group_index: int, layout: str) -> None:
    """把同一组内的卡片布局同步为同一个值（组级语义，调用方需在事务内）。"""

    ChannelPageCard.objects.filter(channel_code=channel_code, group_index=group_index).exclude(
        layout=layout
    ).update(layout=layout)


def _parse_sort(value) -> int:
    try:
        sort_order = int(value)
    except (TypeError, ValueError):
        raise ChannelPageCardError("SORT_INVALID", "排序必须是非负整数。") from None
    if sort_order < 0 or sort_order > MAX_SORT_ORDER:
        raise ChannelPageCardError("SORT_INVALID", f"排序必须是 0–{MAX_SORT_ORDER} 的整数。")
    return sort_order


def serialize_card(card: ChannelPageCard) -> dict:
    page = card.activity_page
    return {
        "id": str(card.public_id),
        "channel_code": card.channel_code,
        "group_index": card.group_index,
        "image_url": card.image_url,
        "link_url": card.link_url,
        "activity_page": (
            {
                "id": str(page.public_id),
                "kind": page.kind,
                "external_id": page.external_id,
                "title": page.title,
                "enabled": page.enabled,
                "local_path": _page_local_path(page),
            }
            if page
            else None
        ),
        "sort_order": card.sort_order,
        "is_active": card.is_active,
        "layout": card.layout,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }


def _page_local_path(page: ActivityPage) -> str:
    if page.kind == ActivityPage.Kind.STORE:
        prefix = "store"
    elif page.kind == ActivityPage.Kind.MARKETING:
        prefix = "marketing"
    else:
        prefix = "active"
    return f"/{prefix}/{page.external_id}"


def resolved_href(card: ChannelPageCard, channel_code: str) -> str:
    """购物端实际跳转：绑定落地页优先；页面停用（下架/失效）回退频道列表页。

    未绑定时沿用 13.8 规则的 ``link_url`` 原值。
    """

    page = card.activity_page
    if page is not None:
        if not page.enabled:
            return f"/minihome/{channel_code}"
        return _page_local_path(page)
    return card.link_url


def storefront_cards(channel_code: str) -> list[ChannelPageCard]:
    """购物端读：去重 → 店铺页优先 → 按频道上限截断（ADR-0002，2026-11-26）。

    - 同一落地页只保留第一张（真站同一活动会同时挂 joyfumi/m. 两条卡）；
    - 超出上限时优先保留店铺页卡，其余按组序号 + sort_order；
    - 展示顺序保持原样（组序号 + sort_order），只在「保留谁」上做优先级；
    - 上限来自 :func:`channel_card_limit`（默认 3，``None`` 不截断）。
    """

    code = str(channel_code or "").strip()
    if not code:
        raise ChannelPageCardError("CHANNEL_REQUIRED", "缺少 channel 参数。")
    rows = list(
        ChannelPageCard.objects.filter(channel_code=code, is_active=True)
        .select_related("activity_page")
        .order_by("group_index", "sort_order", "public_id")
    )

    unique: list[ChannelPageCard] = []
    seen_pages: set[tuple] = set()
    for row in rows:
        page = row.activity_page
        key = (page.kind, page.external_id) if page else ("card", row.pk)
        if key in seen_pages:
            continue
        seen_pages.add(key)
        unique.append(row)

    limit = channel_card_limit(code)
    if limit is not None and len(unique) > limit:
        keep_order = sorted(
            unique,
            key=lambda row: (
                0 if (row.activity_page and row.activity_page.kind == ActivityPage.Kind.STORE) else 1,
                row.group_index,
                row.sort_order,
            ),
        )
        kept = {row.pk for row in keep_order[:limit]}
        unique = [row for row in unique if row.pk in kept]
    return unique


def storefront_groups(rows: list[ChannelPageCard]) -> list[dict]:
    """按截断后的生效卡片重算组概览（空组不再出现在 payload 里）。"""

    groups: dict[int, dict] = {}
    for row in rows:
        group = groups.get(row.group_index)
        if group is None:
            groups[row.group_index] = {
                "group_index": row.group_index,
                "layout": row.layout,
                "count": 1,
            }
        else:
            group["count"] += 1
    return [groups[key] for key in sorted(groups)]


def channel_options() -> list[dict]:
    """管理端频道下拉：9 个导航可见的一级频道（13.1②口径）。

    在频道页 banner 清单基础上过滤掉 ``NAV_HIDDEN_ROOT_SLUGS``（隐藏品类
    的直链保留，但活动卡片配置下拉不出现）；引用常量不改 catalog 层。
    """

    from catalog.search_views import NAV_HIDDEN_ROOT_SLUGS
    from content.channel_banner_services import channel_options as _options

    return [item for item in _options() if item["slug"] not in NAV_HIDDEN_ROOT_SLUGS]


def create_card(*, payload: dict) -> ChannelPageCard:
    channel_code = validate_channel_code(payload.get("channel_code"))
    image_url = validate_image_url(payload.get("image_url"))
    link_url = validate_link_url(payload.get("link_url"))
    is_active = bool(payload.get("is_active", payload.get("enabled", True)))
    group_index = validate_group_index(payload.get("group_index", 0))
    provided_layout = str(payload.get("layout") or "").strip()
    layout = validate_layout(provided_layout) if provided_layout else None
    activity_page = validate_activity_page(payload.get("activity_page"))
    with transaction.atomic():
        if payload.get("sort_order") in (None, ""):
            # 未指定排序时追加到该**组**末尾，避免插队打乱现有顺序。
            last = (
                ChannelPageCard.objects.filter(channel_code=channel_code, group_index=group_index)
                .order_by("-sort_order")
                .values_list("sort_order", flat=True)
                .first()
            )
            sort_order = (last or 0) + 1
        else:
            sort_order = _parse_sort(payload.get("sort_order"))
        # 布局是组级属性：没显式传就沿用该组现有布局，避免同组混用。
        card = ChannelPageCard.objects.create(
            channel_code=channel_code,
            group_index=group_index,
            image_url=image_url,
            link_url=link_url,
            activity_page=activity_page,
            sort_order=sort_order,
            is_active=is_active,
            layout=layout or group_layout(channel_code, group_index),
        )
        if layout is not None:
            _sync_group_layout(channel_code, group_index, layout)
        return card


def update_card(card: ChannelPageCard, *, payload: dict) -> ChannelPageCard:
    fields = []
    channel_changed = False
    group_changed = False
    if "channel_code" in payload and payload.get("channel_code") != card.channel_code:
        card.channel_code = validate_channel_code(payload.get("channel_code"))
        fields.append("channel_code")
        channel_changed = True
    if "group_index" in payload and payload.get("group_index") != card.group_index:
        card.group_index = validate_group_index(payload.get("group_index"))
        fields.append("group_index")
        group_changed = True
    if "image_url" in payload:
        card.image_url = validate_image_url(payload.get("image_url"))
        fields.append("image_url")
    if "link_url" in payload:
        card.link_url = validate_link_url(payload.get("link_url"))
        fields.append("link_url")
    if "activity_page" in payload:
        card.activity_page = validate_activity_page(payload.get("activity_page"))
        fields.append("activity_page")
    if "sort_order" in payload:
        card.sort_order = _parse_sort(payload.get("sort_order"))
        fields.append("sort_order")
    if "is_active" in payload or "enabled" in payload:
        raw = payload.get("is_active", payload.get("enabled"))
        card.is_active = bool(raw)
        fields.append("is_active")
    provided_layout = str(payload.get("layout") or "").strip()
    layout = validate_layout(provided_layout) if provided_layout else None
    if layout is not None:
        card.layout = layout
        fields.append("layout")
    elif channel_changed or group_changed:
        # 换频道/换组但没指定布局：跟随目标组，保持「同一组共用一个布局」。
        card.layout = group_layout(card.channel_code, card.group_index)
        fields.append("layout")
    with transaction.atomic():
        if fields:
            card.save(update_fields=[*fields, "updated_at"])
        if layout is not None:
            _sync_group_layout(card.channel_code, card.group_index, layout)
    return card


def move_card(card: ChannelPageCard, *, direction: str) -> None:
    """**同组内**上移/下移：与相邻条目交换 sort_order（重复值先压实）。"""

    direction = str(direction or "").strip().lower()
    if direction not in {"up", "down"}:
        raise ChannelPageCardError("DIRECTION_INVALID", "移动方向只能是 up 或 down。")

    with transaction.atomic():
        rows = list(
            ChannelPageCard.objects.filter(
                channel_code=card.channel_code, group_index=card.group_index
            )
            .select_for_update()
            .order_by("sort_order", "pk")
        )
        index = next((i for i, row in enumerate(rows) if row.pk == card.pk), None)
        if index is None:
            raise ChannelPageCardError("CARD_NOT_FOUND", "活动卡片不存在。", 404)
        target = index - 1 if direction == "up" else index + 1
        if target < 0 or target >= len(rows):
            raise ChannelPageCardError("MOVE_AT_EDGE", "已经在最顶/最底，无法继续移动。")
        rows[index], rows[target] = rows[target], rows[index]
        for position, row in enumerate(rows, start=1):
            row.sort_order = position
            row.save(update_fields=["sort_order", "updated_at"])
        card.sort_order = next(row.sort_order for row in rows if row.pk == card.pk)


def public_cards(channel_code: str) -> list[ChannelPageCard]:
    """购物端读：该频道 is_active 的条目，按组序号 + sort_order 升序。"""

    code = str(channel_code or "").strip()
    if not code:
        raise ChannelPageCardError("CHANNEL_REQUIRED", "缺少 channel 参数。")
    return list(
        ChannelPageCard.objects.filter(channel_code=code, is_active=True).order_by(
            "group_index", "sort_order", "public_id"
        )
    )
