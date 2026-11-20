"""频道落地页（``/minihome/<code>``）轮播图：管理端 CRUD / 排序 / 公开读取。

与 ``campaign_services`` 同一套纪律：独立模型（``ChannelBanner``）承接高频
运营对象，不进 CMS 版本快照；``channel_code`` 只接受现有 minihome 频道，
图片只接受本地 ``/media/`` 路径（禁止外链 CDN），跳转链接只允许站内路径。
"""

import re

from django.db import transaction

from content.models import ChannelBanner

# 13.8 链接规则：以 http(s)://、//、www. 开头按外链原样使用（不改写），
# 以单个 / 开头视为站内路径；其余（javascript: 等）仍拒绝。
_HREF_PATTERN = re.compile(r"^(?:https?://|//|www\.|/(?!/))\S*$", re.IGNORECASE)
_MEDIA_PREFIX = "/media/"
MAX_SORT_ORDER = 9999


class ChannelBannerError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _clean(value, *, field: str, max_length: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ChannelBannerError("FIELD_REQUIRED", f"{field}不能为空。")
    if len(text) > max_length:
        raise ChannelBannerError("FIELD_TOO_LONG", f"{field}不能超过 {max_length} 个字符。")
    return text


def channel_codes() -> set[str]:
    """现有 minihome 频道 code 集合（与购物端 ``root_channel_codes`` 同源）。

    这里直接查 ``CategoryMapping`` 的 ``minihome:%`` 映射，避开 catalog 视图层
    的序列化逻辑；admin 下拉另走 ``channel_options()`` 带出类目名。
    """

    from catalog.models import CategoryMapping

    return {
        source_id.removeprefix("minihome:")
        for source_id in CategoryMapping.objects.filter(
            source_category__source_id__startswith="minihome:",
            local_category__depth=0,
        ).values_list("source_category__source_id", flat=True)
    }


def validate_channel_code(value) -> str:
    code = _clean(value, field="频道", max_length=64, required=True)
    if code not in channel_codes():
        raise ChannelBannerError(
            "CHANNEL_CODE_INVALID", "频道不存在或不是可配置的一级频道。"
        )
    return code


def validate_image_url(value) -> str:
    image = _clean(value, field="图片地址", max_length=1000, required=True)
    if not image.startswith(_MEDIA_PREFIX) or any(ch.isspace() for ch in image):
        raise ChannelBannerError(
            "IMAGE_URL_INVALID", "图片必须使用本站 /media/ 路径（不支持外部链接）。"
        )
    return image


def validate_href(value) -> str:
    """13.8：外链（http(s)://、//、www. 开头）原样保存；否则视为站内路径。"""

    href = str(value or "").strip()
    if not href:
        return ""
    if len(href) > 1000:
        raise ChannelBannerError("FIELD_TOO_LONG", "跳转链接不能超过 1000 个字符。")
    if not _HREF_PATTERN.match(href):
        raise ChannelBannerError(
            "HREF_INVALID",
            "跳转链接需以 / 开头（站内路径），或以 http(s)://、//、www. 开头（外链原样跳转）。",
        )
    return href


def _parse_sort(value) -> int:
    try:
        sort_order = int(value)
    except (TypeError, ValueError):
        raise ChannelBannerError("SORT_INVALID", "排序必须是非负整数。") from None
    if sort_order < 0 or sort_order > MAX_SORT_ORDER:
        raise ChannelBannerError(
            "SORT_INVALID", f"排序必须是 0–{MAX_SORT_ORDER} 的整数。"
        )
    return sort_order


def serialize_banner(banner: ChannelBanner) -> dict:
    return {
        "id": str(banner.public_id),
        "channel_code": banner.channel_code,
        "image_url": banner.image_url,
        "href": banner.href,
        "sort_order": banner.sort_order,
        "enabled": banner.enabled,
        "created_at": banner.created_at.isoformat(),
        "updated_at": banner.updated_at.isoformat(),
    }


def channel_options() -> list[dict]:
    """管理端频道下拉：有 ``channel_code`` 的一级类目（含中英文名）。

    排序沿用类目表口径（path / sort_order / pk），与购物端频道清单一致。
    """

    from catalog.models import LocalCategory
    from catalog.search_views import root_channel_codes

    mapped = root_channel_codes()
    rows = LocalCategory.objects.filter(pk__in=mapped.keys()).order_by(
        "path", "sort_order", "pk"
    )
    return [
        {
            "channel_code": mapped[row.pk],
            "slug": row.slug,
            "name": row.name_en or row.name,
            "name_zh": row.name_zh or row.name,
        }
        for row in rows
    ]


def create_banner(*, payload: dict) -> ChannelBanner:
    channel_code = validate_channel_code(payload.get("channel_code"))
    image_url = validate_image_url(payload.get("image_url"))
    href = validate_href(payload.get("href"))
    enabled = bool(payload.get("enabled", True))
    with transaction.atomic():
        if payload.get("sort_order") in (None, ""):
            # 未指定排序时追加到该频道末尾，避免插队打乱现有轮播顺序。
            last = (
                ChannelBanner.objects.filter(channel_code=channel_code)
                .order_by("-sort_order")
                .values_list("sort_order", flat=True)
                .first()
            )
            sort_order = (last or 0) + 1
        else:
            sort_order = _parse_sort(payload.get("sort_order"))
        return ChannelBanner.objects.create(
            channel_code=channel_code,
            image_url=image_url,
            href=href,
            sort_order=sort_order,
            enabled=enabled,
        )


def update_banner(banner: ChannelBanner, *, payload: dict) -> ChannelBanner:
    fields = []
    if "channel_code" in payload and payload.get("channel_code") != banner.channel_code:
        banner.channel_code = validate_channel_code(payload.get("channel_code"))
        fields.append("channel_code")
    if "image_url" in payload:
        banner.image_url = validate_image_url(payload.get("image_url"))
        fields.append("image_url")
    if "href" in payload:
        banner.href = validate_href(payload.get("href"))
        fields.append("href")
    if "sort_order" in payload:
        banner.sort_order = _parse_sort(payload.get("sort_order"))
        fields.append("sort_order")
    if "enabled" in payload:
        banner.enabled = bool(payload.get("enabled"))
        fields.append("enabled")
    if fields:
        banner.save(update_fields=[*fields, "updated_at"])
    return banner


def move_banner(banner: ChannelBanner, *, direction: str) -> None:
    """同频道内上移/下移：与相邻条目交换 sort_order（重复值先压实）。"""

    direction = str(direction or "").strip().lower()
    if direction not in {"up", "down"}:
        raise ChannelBannerError("DIRECTION_INVALID", "移动方向只能是 up 或 down。")

    with transaction.atomic():
        rows = list(
            ChannelBanner.objects.filter(channel_code=banner.channel_code)
            .select_for_update()
            .order_by("sort_order", "pk")
        )
        index = next((i for i, row in enumerate(rows) if row.pk == banner.pk), None)
        if index is None:
            raise ChannelBannerError("BANNER_NOT_FOUND", "频道 banner 不存在。", 404)
        target = index - 1 if direction == "up" else index + 1
        if target < 0 or target >= len(rows):
            raise ChannelBannerError("MOVE_AT_EDGE", "已经在最顶/最底，无法继续移动。")
        rows[index], rows[target] = rows[target], rows[index]
        for position, row in enumerate(rows, start=1):
            row.sort_order = position
            row.save(update_fields=["sort_order", "updated_at"])
        banner.sort_order = next(row.sort_order for row in rows if row.pk == banner.pk)


def public_banners(channel_code: str) -> list[ChannelBanner]:
    """购物端读：只返回该频道 enabled 的条目，按 sort_order。"""

    code = str(channel_code or "").strip()
    if not code:
        raise ChannelBannerError("CHANNEL_CODE_REQUIRED", "缺少 channel_code 参数。")
    return list(
        ChannelBanner.objects.filter(channel_code=code, enabled=True).order_by(
            "sort_order", "public_id"
        )
    )
