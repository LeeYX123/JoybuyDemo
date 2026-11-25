"""活动页/店铺页的读写与序列化（2026-11-25）。

口径：
- 商城公开接口只读：按 ``external_id`` 取 enabled 页面，返回 hero + 分区
  （BANNER 图 / PRODUCTS 楼层 + 商品卡）。商品卡取本地库数据，价格用
  库内正常售价（与 PDP 一致），不倒计时、不发券（用户 2026-11-25 拍板）。
- 管理端接口写：页面/分区/选品 CRUD，字段校验与排序维护都收敛在这里，
  视图层只做参数搬运与权限。
"""

import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Min

from content.models import ActivityPage, ActivitySection, ActivitySectionProduct


class ActivityPageError(Exception):
    """带业务码的校验错误（视图层转成 StaffApiError）。"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


PAGE_KINDS = {choice.value for choice in ActivityPage.Kind}
SECTION_KINDS = {choice.value for choice in ActivitySection.Kind}
MAX_SECTIONS = 40
MAX_SECTION_PRODUCTS = 120


# ---------------------------------------------------------------------------
# 读：公开 payload
# ---------------------------------------------------------------------------


def _image_for_spus(spu_ids) -> dict[int, str]:
    """SPU → 首张本地画廊图（与频道楼层同口径，一次查询）。"""

    from django.contrib.contenttypes.models import ContentType

    from catalog.models import Spu
    from media.models import MediaUsage
    from media.storage import media_url

    if not spu_ids:
        return {}
    spu_type = ContentType.objects.get_for_model(Spu)
    usages = (
        MediaUsage.objects.filter(
            content_type=spu_type, object_id__in=set(spu_ids), role="gallery"
        )
        .select_related("asset")
        .order_by("object_id", "sort_order", "pk")
    )
    result: dict[int, str] = {}
    for usage in usages:
        result.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return result


def _prices_for_spus(spu_ids, *, market) -> dict[int, tuple[str | None, str]]:
    """SPU → (最低 ACTIVE 报价字符串, 币种码)；market 为空时取全站最低价。"""

    from offers.models import Offer

    if not spu_ids:
        return {}
    queryset = Offer.objects.filter(
        sku__spu_id__in=set(spu_ids), status=Offer.Status.ACTIVE
    )
    if market is not None:
        queryset = queryset.filter(market=market)
    rows = (
        queryset.values("sku__spu_id")
        .annotate(lowest=Min("current_price"))
        .order_by()
    )
    lowest = {row["sku__spu_id"]: row["lowest"] for row in rows}
    currencies = {
        row["sku__spu_id"]: row["currency__code"]
        for row in queryset.values("sku__spu_id", "currency__code").order_by()
        if row["currency__code"]
    }
    return {
        spu_id: (
            str(lowest[spu_id]) if lowest.get(spu_id) is not None else None,
            currencies.get(spu_id, "GBP"),
        )
        for spu_id in lowest
    }


def _retail_price(spu) -> str | None:
    value = getattr(spu, "retail_price", None)
    if isinstance(value, Decimal):
        return format(value, "f")
    return None


def _prices_for_skus(sku_ids, *, market) -> dict[int, tuple[str | None, str]]:
    """SKU → (最低 ACTIVE 报价字符串, 币种码)。多规格商品按规格各自定价。"""

    from offers.models import Offer

    if not sku_ids:
        return {}
    queryset = Offer.objects.filter(sku_id__in=set(sku_ids), status=Offer.Status.ACTIVE)
    if market is not None:
        queryset = queryset.filter(market=market)
    rows = queryset.values("sku_id").annotate(lowest=Min("current_price")).order_by()
    lowest = {row["sku_id"]: row["lowest"] for row in rows}
    currencies = {
        row["sku_id"]: row["currency__code"]
        for row in queryset.values("sku_id", "currency__code").order_by()
        if row["currency__code"]
    }
    return {
        sku_id: (
            str(lowest[sku_id]) if lowest.get(sku_id) is not None else None,
            currencies.get(sku_id, "GBP"),
        )
        for sku_id in lowest
    }


def serialize_section_items(items, *, market, locale_code: str = "en-GB") -> list[dict]:
    """楼层位次 → 商品卡（严格按位次顺序）。

    与 ``serialize_page_products`` 的差别：支持同一 SPU 的多个规格各占一卡
    （2026-11-25，真站同款不同尺寸分卡展示）；价格优先取该规格的报价，
    无 SKU 时回退 SPU 最低价，再回退后台零售价。
    """

    items = list(items)
    if not items:
        return []

    from catalog.models import Spu

    spu_ids: list[int] = []
    for item in items:
        if item.spu_id not in spu_ids:
            spu_ids.append(item.spu_id)
    sku_ids = [item.sku_id for item in items if item.sku_id]

    images = _image_for_spus(spu_ids)
    prices_spu = _prices_for_spus(spu_ids, market=market)
    prices_sku = _prices_for_skus(sku_ids, market=market)
    spus = {
        spu.pk: spu
        for spu in Spu.objects.filter(pk__in=spu_ids)
        .select_related("brand", "local_category")
        .prefetch_related("translations")
    }

    cards: list[dict] = []
    for item in items:
        spu = spus.get(item.spu_id)
        if spu is None or spu.status != "ACTIVE":
            continue
        rows = list(spu.translations.all())
        title = next((row.title for row in rows if row.locale == locale_code), "") or next(
            (row.title for row in rows), ""
        )
        price, currency = prices_spu.get(spu.pk, (None, "GBP"))
        sku_public_id = None
        if item.sku_id:
            price, currency = prices_sku.get(item.sku_id, (price, currency))
            sku_public_id = str(item.sku.public_id) if item.sku_id else None
        href = f"/p/{spu.public_id}"
        if sku_public_id:
            href = f"{href}?sku={sku_public_id}"
        cards.append(
            {
                # 同一 SPU 可能占多个位次，前端 key 必须用位次而不是 SPU。
                "item_key": str(item.public_id),
                "spu_public_id": str(spu.public_id),
                "sku_public_id": sku_public_id,
                "title": title,
                "brand": spu.brand.name if getattr(spu, "brand_id", None) else "",
                "category_slug": spu.local_category.slug if spu.local_category_id else None,
                "price": _retail_price(spu) or price,
                "list_price": price,
                "currency": currency,
                "image_path": images.get(spu.pk, ""),
                "href": href,
            }
        )
    return cards


def serialize_page_products(spus, *, market, locale_code: str = "en-GB") -> list[dict]:
    """SPU 列表 → 商品卡（兼容入口：无 SKU 维度时按 SPU 顺序输出）。"""

    from content.models import ActivitySectionProduct as _Item

    proxies = [
        _Item(
            public_id=spu.public_id,
            spu=spu,
            spu_id=spu.pk,
        )
        for spu in spus
    ]
    return serialize_section_items(proxies, market=market, locale_code=locale_code)


def activity_page_payload(
    page: ActivityPage, *, market=None, locale_code: str = "en-GB"
) -> dict:
    """公开 payload：hero + 分区（BANNER 图 / PRODUCTS 商品楼层）。"""

    sections = list(
        page.sections.prefetch_related(
            "items__spu__translations",
            "items__spu__brand",
            "items__spu__local_category",
            "items__sku",
        ).order_by("sort_order", "pk")
    )

    payload_sections = []
    for section in sections:
        data = {
            "public_id": str(section.public_id),
            "kind": section.kind,
            "title": section.title,
            "title_zh": section.title_zh,
            "title_color": section.title_color,
            "title_background": section.title_background,
            "image_url": section.image_url,
            "href": section.href,
            "columns": section.columns,
            "show_more": section.show_more,
            "extra": section.extra or {},
            "products": [],
        }
        if section.kind == ActivitySection.Kind.PRODUCTS:
            data["products"] = serialize_section_items(
                section.items.all(), market=market, locale_code=locale_code
            )
        payload_sections.append(data)

    return {
        "public_id": str(page.public_id),
        "kind": page.kind,
        "external_id": page.external_id,
        "title": page.title,
        "title_zh": page.title_zh,
        "store_name": page.store_name,
        "logo_image": page.logo_image,
        "hero_image": page.hero_image,
        "background_color": page.background_color,
        "source_url": page.source_url,
        "sections": payload_sections,
    }


# ---------------------------------------------------------------------------
# 写：管理端
# ---------------------------------------------------------------------------


def _clean_text(value, *, field: str, max_length: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ActivityPageError("FIELD_REQUIRED", f"{field} 不能为空。")
    if len(text) > max_length:
        raise ActivityPageError("FIELD_TOO_LONG", f"{field} 超长（>{max_length}）。")
    return text


def create_page(payload: dict) -> ActivityPage:
    kind = str(payload.get("kind") or "").strip().upper()
    if kind not in PAGE_KINDS:
        raise ActivityPageError("KIND_INVALID", "页面类型不正确。")
    external_id = _clean_text(
        payload.get("external_id"), field="真站页面 ID", max_length=64, required=True
    )
    if ActivityPage.objects.filter(kind=kind, external_id=external_id).exists():
        raise ActivityPageError("PAGE_EXISTS", "同类型同 ID 的页面已存在。", 409)
    with transaction.atomic():
        count = ActivityPage.objects.count()
        return ActivityPage.objects.create(
            kind=kind,
            external_id=external_id,
            title=_clean_text(payload.get("title"), field="页面标题", max_length=200, required=True),
            title_zh=_clean_text(payload.get("title_zh"), field="中文标题", max_length=200),
            store_name=_clean_text(payload.get("store_name"), field="店铺名", max_length=160),
            source_url=_clean_text(payload.get("source_url"), field="来源地址", max_length=500),
            hero_image=_clean_text(payload.get("hero_image"), field="Hero 图", max_length=1000),
            background_color=_clean_text(
                payload.get("background_color"), field="底色", max_length=16
            ),
            enabled=bool(payload.get("enabled", True)),
            sort_order=int(payload.get("sort_order") or count),
        )


def update_page(page: ActivityPage, payload: dict) -> ActivityPage:
    fields = []
    if "title" in payload:
        page.title = _clean_text(
            payload.get("title"), field="页面标题", max_length=200, required=True
        )
        fields.append("title")
    if "title_zh" in payload:
        page.title_zh = _clean_text(payload.get("title_zh"), field="中文标题", max_length=200)
        fields.append("title_zh")
    if "store_name" in payload:
        page.store_name = _clean_text(
            payload.get("store_name"), field="店铺名", max_length=160
        )
        fields.append("store_name")
    if "hero_image" in payload:
        page.hero_image = _clean_text(
            payload.get("hero_image"), field="Hero 图", max_length=1000
        )
        fields.append("hero_image")
    if "background_color" in payload:
        page.background_color = _clean_text(
            payload.get("background_color"), field="底色", max_length=16
        )
        fields.append("background_color")
    if "enabled" in payload:
        page.enabled = bool(payload.get("enabled"))
        fields.append("enabled")
    if "sort_order" in payload:
        page.sort_order = int(payload.get("sort_order") or 0)
        fields.append("sort_order")
    if fields:
        page.save(update_fields=[*fields, "updated_at"])
    return page


COLOUR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))$")


def _clean_colour(value, *, field: str) -> str:
    """颜色只允许空串、#hex 或 rgb()/rgba()（前端直接写进 inline style）。"""

    text = str(value or "").strip()
    if not text:
        return ""
    if not COLOUR_RE.match(text):
        raise ActivityPageError(
            "COLOUR_INVALID", f"{field} 需为 #hex 或 rgb()/rgba()，收到：{text[:20]}"
        )
    return text


def create_section(page: ActivityPage, payload: dict) -> ActivitySection:
    kind = str(payload.get("kind") or ActivitySection.Kind.PRODUCTS).strip().upper()
    if kind not in SECTION_KINDS:
        raise ActivityPageError("SECTION_KIND_INVALID", "分区类型不正确。")
    if page.sections.count() >= MAX_SECTIONS:
        raise ActivityPageError("SECTION_LIMIT", f"分区最多 {MAX_SECTIONS} 个。")
    if kind == ActivitySection.Kind.BANNER:
        image = _clean_text(payload.get("image_url"), field="图片", max_length=1000, required=True)
        title = ""
    else:
        image = _clean_text(payload.get("image_url"), field="图片", max_length=1000)
        title = _clean_text(payload.get("title"), field="模块标题", max_length=200)
    columns = int(payload.get("columns") or 5)
    if columns not in (4, 5):
        raise ActivityPageError("COLUMNS_INVALID", "商品列数只支持 4 或 5。")
    with transaction.atomic():
        count = page.sections.count()
        return ActivitySection.objects.create(
            page=page,
            kind=kind,
            title=title,
            title_zh=_clean_text(payload.get("title_zh"), field="中文标题", max_length=200),
            title_color=_clean_colour(payload.get("title_color"), field="标题字色"),
            title_background=_clean_colour(payload.get("title_background"), field="标题底色"),
            image_url=image,
            href=_clean_text(payload.get("href"), field="跳转链接", max_length=1000),
            columns=columns,
            show_more=bool(payload.get("show_more", False)),
            sort_order=int(payload.get("sort_order") or count),
        )


def update_section(section: ActivitySection, payload: dict) -> ActivitySection:
    fields = []
    if "title" in payload and section.kind == ActivitySection.Kind.PRODUCTS:
        section.title = _clean_text(payload.get("title"), field="模块标题", max_length=200)
        fields.append("title")
    if "title_zh" in payload:
        section.title_zh = _clean_text(
            payload.get("title_zh"), field="中文标题", max_length=200
        )
        fields.append("title_zh")
    if "title_color" in payload:
        section.title_color = _clean_colour(payload.get("title_color"), field="标题字色")
        fields.append("title_color")
    if "title_background" in payload:
        section.title_background = _clean_colour(
            payload.get("title_background"), field="标题底色"
        )
        fields.append("title_background")
    if "image_url" in payload:
        section.image_url = _clean_text(
            payload.get("image_url"), field="图片", max_length=1000
        )
        fields.append("image_url")
    if "href" in payload:
        section.href = _clean_text(payload.get("href"), field="跳转链接", max_length=1000)
        fields.append("href")
    if "columns" in payload:
        columns = int(payload.get("columns") or 5)
        if columns not in (4, 5):
            raise ActivityPageError("COLUMNS_INVALID", "商品列数只支持 4 或 5。")
        section.columns = columns
        fields.append("columns")
    if "show_more" in payload:
        section.show_more = bool(payload.get("show_more"))
        fields.append("show_more")
    if "sort_order" in payload:
        section.sort_order = int(payload.get("sort_order") or 0)
        fields.append("sort_order")
    if fields:
        section.save(update_fields=[*fields, "updated_at"])
    return section


def replace_section_products(section: ActivitySection, spu_public_ids: list[str]) -> int:
    """整体替换楼层选品（按传入顺序）。返回写入条数。"""

    from catalog.models import Spu

    ids = [str(value).strip() for value in (spu_public_ids or []) if str(value).strip()]
    if len(ids) > MAX_SECTION_PRODUCTS:
        raise ActivityPageError("PRODUCT_LIMIT", f"单楼层商品最多 {MAX_SECTION_PRODUCTS} 个。")
    if len(set(ids)) != len(ids):
        raise ActivityPageError("PRODUCT_DUPLICATED", "同一楼层内商品不能重复。")
    spus = {str(spu.public_id): spu for spu in Spu.objects.filter(public_id__in=ids)}
    missing = [value for value in ids if value not in spus]
    if missing:
        raise ActivityPageError(
            "PRODUCT_NOT_FOUND", f"商品不存在：{', '.join(missing[:3])}", 404
        )
    with transaction.atomic():
        section.items.all().delete()
        ActivitySectionProduct.objects.bulk_create(
            [
                ActivitySectionProduct(section=section, spu=spus[value], sort_order=index)
                for index, value in enumerate(ids)
            ]
        )
    return len(ids)


def serialize_page(page: ActivityPage, *, include_products: bool = True) -> dict:
    """管理端详情：页面 + 分区 + 商品 id 列表（编辑用）。"""

    sections = []
    for section in page.sections.all().order_by("sort_order", "pk"):
        data = {
            "public_id": str(section.public_id),
            "kind": section.kind,
            "title": section.title,
            "title_zh": section.title_zh,
            "title_color": section.title_color,
            "title_background": section.title_background,
            "image_url": section.image_url,
            "href": section.href,
            "columns": section.columns,
            "show_more": section.show_more,
            "extra": section.extra or {},
            "sort_order": section.sort_order,
        }
        if include_products and section.kind == ActivitySection.Kind.PRODUCTS:
            data["products"] = [
                {
                    "spu_public_id": str(item.spu.public_id),
                    "title": (
                        item.spu.translations.first().title
                        if item.spu.translations.exists()
                        else ""
                    ),
                    "image_path": "",
                    "price": str(item.spu.retail_price) if item.spu.retail_price else None,
                    "sort_order": item.sort_order,
                }
                for item in section.items.select_related("spu").order_by("sort_order", "pk")
            ]
        sections.append(data)
    return {
        "public_id": str(page.public_id),
        "kind": page.kind,
        "external_id": page.external_id,
        "title": page.title,
        "title_zh": page.title_zh,
        "store_name": page.store_name,
        "logo_image": page.logo_image,
        "source_url": page.source_url,
        "hero_image": page.hero_image,
        "background_color": page.background_color,
        "enabled": page.enabled,
        "sort_order": page.sort_order,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
        "sections": sections,
    }
