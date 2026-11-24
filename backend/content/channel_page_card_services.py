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

from content.models import ChannelPageCard

MAX_SORT_ORDER = 9999
MAX_GROUP_INDEX = 99

DEFAULT_LAYOUT = ChannelPageCard.Layout.ROW3


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
    return {
        "id": str(card.public_id),
        "channel_code": card.channel_code,
        "group_index": card.group_index,
        "image_url": card.image_url,
        "link_url": card.link_url,
        "sort_order": card.sort_order,
        "is_active": card.is_active,
        "layout": card.layout,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }


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
