"""首页可运营卡片：管理端 CRUD / 排序 / storefront 注入。

``section`` 区分两个首页模块，共用一张表（``HomeCampaignCard``）与一套
CRUD/排序逻辑：

- ``campaign``：「Offers for you」活动卡片 → 覆盖快照 ``campaign_grid``；
- ``discovery``：「品类发现」tiles 卡片 → 覆盖快照 ``link_grid``；
- ``weekly``：「每周甄选」活动卡片 → 覆盖 ``weekly_picks``（批次 O 14.2）。

快照本身只读，保证版本回滚不被运营数据污染。
"""

import re

from django.db import transaction

from content.models import CmsModule, HomeCampaignCard

# campaign：5 列 × 2 排的 10 宫格；discovery：固定 6 张；
# weekly：一排 6 张活动卡（批次 O 14.2 验收口径）。
SECTION_LIMITS = {"campaign": 10, "discovery": 12, "weekly": 6}
MAX_CARDS = SECTION_LIMITS["campaign"]  # 兼容旧引用

# 首页品类发现不展示的根品类（需求文档03 14.1：只影响该模块，品类与导航
# 不受影响；卡片数据保留，后台仍可管理）。
DISCOVERY_HIDDEN_SLUGS = frozenset({"pet-supplies", "baby-toddler", "games-accessories"})
# 14.1：该模块固定只展示 6 张（后台容量仍为 12，便于替换/停用）。
DISCOVERY_VISIBLE_LIMIT = 6

# storefront 注入时各自覆盖的 CMS 模块类型。
SECTION_MODULE_TYPES = {
    "campaign": "campaign_grid",
    "discovery": "link_grid",
    "weekly": "weekly_picks",
}

# 13.8 链接规则：以 http(s)://、//、www. 开头按外链原样使用（不改写），
# 以单个 / 开头视为站内路径；其余（javascript: 等）仍拒绝。
_HREF_PATTERN = re.compile(r"^(?:https?://|//|www\.|/(?!/))\S*$", re.IGNORECASE)


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
    """13.8：外链（http(s)://、//、www. 开头）原样保存；否则视为站内路径。"""

    href = (value or "").strip()
    if not href:
        return ""
    if not _HREF_PATTERN.match(href):
        raise CampaignCardError(
            "HREF_INVALID",
            "跳转链接需以 / 开头（站内路径），或以 http(s)://、//、www. 开头（外链原样跳转）。",
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


_DISCOVERY_CATEGORY_PATTERNS = (
    re.compile(r"[?&]category=([^&#]+)"),
    re.compile(r"^/c/([^/?#]+)"),
)


def _discovery_category_slug(href: str) -> str:
    """品类发现卡片的跳转链接 → 一级 slug（/s?category=x 或 /c/x）。"""

    for pattern in _DISCOVERY_CATEGORY_PATTERNS:
        match = pattern.search(href or "")
        if match:
            return match.group(1)
    return ""


def campaign_payload(section: str = "campaign") -> dict | None:
    """启用中的卡片按顺序组成对应模块的 payload；无卡片返回 None。

    discovery 的模块级标题沿用快照口径（Category discovery / 品类发现），
    连同 variant 一起带上，渲染组件才按 tiles 网格出图。

    品类发现 tiles 与顶部导航同口径（批次 H 验收修复）：按卡片 href 里的
    一级 slug 过滤掉 ``NAV_HIDDEN_ROOT_SLUGS``（只影响展示，不删数据），
    并把名称覆盖为 ``LocalCategory`` 的当前 en/zh 名——卡片图片与跳转仍由
    管理端配置。
    """

    cards = list(
        HomeCampaignCard.objects.filter(section=section, enabled=True).order_by("sort_order", "pk")
    )
    if section == "discovery":
        from catalog.models import LocalCategory
        from catalog.search_views import NAV_HIDDEN_ROOT_SLUGS

        cards = [
            card
            for card in cards
            if _discovery_category_slug(card.href) not in NAV_HIDDEN_ROOT_SLUGS
            and _discovery_category_slug(card.href) not in DISCOVERY_HIDDEN_SLUGS
        ]
        cards = cards[:DISCOVERY_VISIBLE_LIMIT]
        if not cards:
            return None
        slugs = {_discovery_category_slug(card.href) for card in cards}
        categories = {
            category.slug: category
            for category in LocalCategory.objects.filter(slug__in=slugs, depth=0)
        }
        items = []
        for card in cards:
            item = serialize_card(card)
            category = categories.get(_discovery_category_slug(card.href))
            if category is not None:
                # 名称以类目表为准（改名后全站一致）；图片/href 仍取卡片配置。
                item["label"] = category.name_en or category.name
                item["label_zh"] = category.name_zh
            items.append(item)
        payload = {
            "items": items,
            "variant": "tiles",
            "title": "Category discovery",
            "title_zh": "品类发现",
        }
        return payload

    cards = cards[: SECTION_LIMITS.get(section, 10)]
    if not cards:
        return None
    payload = {"items": [serialize_card(card) for card in cards]}
    if section == "weekly":
        payload.update({"title": "Weekly picks", "title_zh": "每周甄选"})
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
