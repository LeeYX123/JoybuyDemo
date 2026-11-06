"""首页可运营卡片：管理端 CRUD / 排序 / storefront 注入。

``section`` 区分两个首页模块，共用一张表（``HomeCampaignCard``）与一套
CRUD/排序逻辑：

- ``campaign``：「Offers for you」活动卡片 → 覆盖快照 ``campaign_grid``；
- ``discovery``：「品类发现」tiles 卡片 → 覆盖快照 ``link_grid``。

快照本身只读，保证版本回滚不被运营数据污染。
"""

import re

from django.db import transaction

from content.models import CmsModule, HomeCampaignCard

# campaign：5 列 × 2 排的 10 宫格；discovery：auto-fill 网格，当前 6 张。
SECTION_LIMITS = {"campaign": 10, "discovery": 12}
MAX_CARDS = SECTION_LIMITS["campaign"]  # 兼容旧引用

# storefront 注入时各自覆盖的 CMS 模块类型。
SECTION_MODULE_TYPES = {"campaign": "campaign_grid", "discovery": "link_grid"}

# 站内路径或外链都允许，但必须以 / 或 http(s) 开头，挡掉 javascript: 等。
_HREF_PATTERN = re.compile(r"^(?:/[^/\s]|https?://)\S*$", re.IGNORECASE)


class CampaignCardError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _clean(value, *, field: str, max_length: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise CampaignCardError("FIELD_REQUIRED", f"{field}不能为空。")
    if len(text) > max_length:
        raise CampaignCardError("FIELD_TOO_LONG", f"{field}不能超过 {max_length} 个字符。")
    return text


def validate_href(value: str) -> str:
    href = (value or "").strip()
    if not href:
        return ""
    if not _HREF_PATTERN.match(href):
        raise CampaignCardError(
            "HREF_INVALID", "跳转链接必须以 / 开头的站内路径或 http(s):// 链接。"
        )
    return href


def serialize_card(card: HomeCampaignCard) -> dict:
    """转成购物端渲染组件认识的 item 结构（含可选双语）。

    campaign 的 item 用 title/subtitle/image_path（CmsCampaignGrid）；
    discovery 的 item 用 label/label_zh/icon_path（CmsLinkGrid tiles）。
    数据库字段统一叫 title/image_url，序列化时按 section 换名。
    """

    if card.section == HomeCampaignCard.Section.DISCOVERY:
        item = {"label": card.title}
        if card.title_zh:
            item["label_zh"] = card.title_zh
        if card.image_url:
            item["icon_path"] = card.image_url
        if card.href:
            item["href"] = card.href
        return item

    item = {"title": card.title, "subtitle": card.subtitle}
    if card.title_zh:
        item["title_zh"] = card.title_zh
    if card.subtitle_zh:
        item["subtitle_zh"] = card.subtitle_zh
    if card.image_url:
        item["image_path"] = card.image_url
    if card.href:
        item["href"] = card.href
    return item


def campaign_payload(section: str = "campaign") -> dict | None:
    """启用中的卡片按顺序组成对应模块的 payload；无卡片返回 None。

    discovery 的模块级标题沿用快照口径（Category discovery / 品类发现），
    连同 variant 一起带上，渲染组件才按 tiles 网格出图。
    """

    cards = list(
        HomeCampaignCard.objects.filter(section=section, enabled=True).order_by("sort_order", "pk")[
            : SECTION_LIMITS.get(section, 10)
        ]
    )
    if not cards:
        return None
    payload = {"items": [serialize_card(card) for card in cards]}
    if section == "discovery":
        payload["variant"] = "tiles"
        payload["title"] = "Category discovery"
        payload["title_zh"] = "品类发现"
    return payload


def create_card(*, payload: dict, section: str = "campaign") -> HomeCampaignCard:
    if section not in SECTION_LIMITS:
        raise CampaignCardError("SECTION_INVALID", "卡片分区不正确。")
    label_field = "名称" if section == "discovery" else "标题"
    title = _clean(payload.get("title"), field=label_field, max_length=60, required=True)
    with transaction.atomic():
        count = HomeCampaignCard.objects.filter(section=section).count()
        limit = SECTION_LIMITS[section]
        if count >= limit:
            raise CampaignCardError(
                "TOO_MANY_CARDS", f"该分区最多 {limit} 张卡片，请先移除或停用现有卡片。"
            )
        # 新卡默认排到本分区启用卡片之后，避免插队打乱现有顺序。
        max_order = next(
            iter(
                HomeCampaignCard.objects.filter(section=section)
                .order_by("-sort_order")
                .values_list("sort_order", flat=True)[:1]
            ),
            0,
        )
        return HomeCampaignCard.objects.create(
            section=section,
            title=title,
            title_zh=_clean(payload.get("title_zh"), field="中文名称", max_length=60),
            subtitle=_clean(payload.get("subtitle"), field="副标题", max_length=120),
            subtitle_zh=_clean(payload.get("subtitle_zh"), field="中文副标题", max_length=120),
            image_url=_clean(payload.get("image_url"), field="图片地址", max_length=1000),
            href=validate_href(payload.get("href")),
            sort_order=max_order + 1,
            enabled=bool(payload.get("enabled", True)),
        )


def update_card(card: HomeCampaignCard, *, payload: dict) -> HomeCampaignCard:
    fields = []
    label_field = "名称" if card.section == HomeCampaignCard.Section.DISCOVERY else "标题"
    if "title" in payload:
        card.title = _clean(payload.get("title"), field=label_field, max_length=60, required=True)
        fields.append("title")
    if "title_zh" in payload:
        card.title_zh = _clean(payload.get("title_zh"), field="中文名称", max_length=60)
        fields.append("title_zh")
    if "subtitle" in payload:
        card.subtitle = _clean(payload.get("subtitle"), field="副标题", max_length=120)
        fields.append("subtitle")
    if "subtitle_zh" in payload:
        card.subtitle_zh = _clean(payload.get("subtitle_zh"), field="中文副标题", max_length=120)
        fields.append("subtitle_zh")
    if "image_url" in payload:
        card.image_url = _clean(payload.get("image_url"), field="图片地址", max_length=1000)
        fields.append("image_url")
    if "href" in payload:
        card.href = validate_href(payload.get("href"))
        fields.append("href")
    if "enabled" in payload:
        card.enabled = bool(payload.get("enabled"))
        fields.append("enabled")
    if fields:
        card.save(update_fields=[*fields, "updated_at"])
    return card


def move_card(card: HomeCampaignCard, *, direction: str) -> None:
    """上移/下移：与相邻卡片交换 sort_order（只在本分区内）。同序值先压实。"""

    direction = str(direction or "").strip().lower()
    if direction not in {"up", "down"}:
        raise CampaignCardError("DIRECTION_INVALID", "移动方向只能是 up 或 down。")

    with transaction.atomic():
        rows = list(
            HomeCampaignCard.objects.filter(section=card.section)
            .select_for_update()
            .order_by("sort_order", "pk")
        )
        index = next((i for i, row in enumerate(rows) if row.pk == card.pk), None)
        if index is None:
            raise CampaignCardError("CARD_NOT_FOUND", "卡片不存在。", 404)
        target = index - 1 if direction == "up" else index + 1
        if target < 0 or target >= len(rows):
            raise CampaignCardError("MOVE_AT_EDGE", "已经在最顶/最底，无法继续移动。")
        # sort_order 可能重复（历史数据），交换前先重排成唯一序再换位。
        for position, row in enumerate(rows, start=1):
            if row.sort_order != position:
                row.sort_order = position
            rows[position - 1] = row
        rows[index], rows[target] = rows[target], rows[index]
        for position, row in enumerate(rows, start=1):
            row.sort_order = position
            row.save(update_fields=["sort_order", "updated_at"])


def import_from_published_snapshot(section: str = "campaign") -> int:
    """把当前发布快照里对应模块的 items 迁进独立表（一次性回填）。

    该 section 已有数据时跳过，避免重复导入。迁移后快照原样保留。
    """

    if HomeCampaignCard.objects.filter(section=section).exists():
        return 0
    module_type = SECTION_MODULE_TYPES[section]
    module = (
        CmsModule.objects.filter(module_type=module_type, page__status="published")
        .order_by("-page__version", "pk")
        .first()
    )
    if module is None:
        return 0
    created = 0
    for order, item in enumerate(module.payload.get("items", []), start=1):
        if not isinstance(item, dict):
            continue
        if section == "discovery":
            title = str(item.get("label") or "").strip()
            title_zh = str(item.get("label_zh") or "").strip()
            image_url = str(item.get("icon_path") or "").strip()
        else:
            title = str(item.get("title") or "").strip()
            title_zh = str(item.get("title_zh") or "").strip()
            image_url = str(item.get("image_path") or "").strip()
        if not title:
            continue
        HomeCampaignCard.objects.create(
            section=section,
            title=title[:60],
            title_zh=title_zh[:60],
            subtitle=str(item.get("subtitle") or "").strip()[:120],
            subtitle_zh=str(item.get("subtitle_zh") or "").strip()[:120],
            image_url=image_url[:1000],
            href=str(item.get("href") or "").strip()[:1000],
            sort_order=order,
            enabled=True,
        )
        created += 1
    return created
