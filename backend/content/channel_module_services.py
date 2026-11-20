"""频道页商品楼层（批次 H，2026-11-19）：公开读取 + 管理端配置。

楼层引用真实 SPU（``ChannelModuleProduct``），购物端按频道取 enabled 楼层，
商品序列化与 ``/api/v1/search`` 同构（``serialize_search_row``），保证
``ProductCard`` 直接复用。管理端接口只允许改标题/排序/开关/商品清单，
不创建或修改商品本身。
"""

from django.db import transaction

from content.models import ChannelModule, ChannelModuleProduct

MAX_TITLE_LENGTH = 120
MAX_SORT_ORDER = 9999
MAX_PRODUCTS = 60


class ChannelModuleError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def channel_root_slug(channel_code: str) -> str:
    """频道 code → 本地一级 slug（面包屑/【更多】落 ``/c/<slug>``）。"""

    from catalog.models import CategoryMapping

    mapping = (
        CategoryMapping.objects.filter(
            source_category__source_id=f"minihome:{channel_code}",
            local_category__depth=0,
        )
        .select_related("local_category")
        .first()
    )
    return mapping.local_category.slug if mapping else ""


def _localized_title(module: ChannelModule, language_code: str) -> str:
    if language_code == "zh" and module.title_zh:
        return module.title_zh
    return module.title_en


def _documents(spu_ids, *, market, locale_code):
    from catalog.models import ProductSearchDocument

    return {
        row.spu_id: row
        for row in ProductSearchDocument.objects.filter(
            market=market, locale_code=locale_code, spu_id__in=spu_ids
        ).select_related("spu", "local_category")
    }


def _gallery_paths(spu_ids) -> dict[int, str]:
    """第一张本地画廊图（与请求 locale 无关，图片不依赖搜索文档口径）。

    中文搜索文档已回退（库里只有 en-GB 文档），若按请求 locale 取文档会
    导致中文频道楼层 image_path 全空（验收 FAIL ①，2026-11-19）。
    """

    from django.contrib.contenttypes.models import ContentType

    from catalog.models import Spu
    from media.models import MediaUsage
    from media.storage import media_url

    if not spu_ids:
        return {}
    spu_type = ContentType.objects.get_for_model(Spu)
    usages = (
        MediaUsage.objects.filter(
            content_type=spu_type,
            object_id__in=set(spu_ids),
            role="gallery",
        )
        .select_related("asset")
        .order_by("object_id", "sort_order", "pk")
    )
    result = {}
    for usage in usages:
        result.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return result


def _fallback_product(spu, image_path: str) -> dict:
    """SPU 没有搜索文档时的兜底序列化（仍带图/价，不让卡片空白）。"""

    from offers.models import Offer

    offer = (
        Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE)
        .order_by("current_price")
        .first()
    )
    price = str(offer.current_price) if offer else None
    translation = spu.translations.first()
    return {
        "spu_public_id": str(spu.public_id),
        "title": translation.title if translation else "",
        "brand": offer.merchant.display_name if offer and offer.merchant_id else "",
        "category_slug": spu.local_category.slug if spu.local_category_id else None,
        "price_min": price,
        "price_max": price,
        "currency": offer.currency.code if offer and offer.currency_id else None,
        "rating_average": None,
        "rating_count": 0,
        "image_path": image_path,
    }


def public_modules(channel_code: str, *, market, locale_code: str, language_code: str) -> dict:
    """购物端频道页楼层：enabled 楼层 + 有序商品（与搜索 item 同构）。

    商品数据（标题/价格/图片）统一取默认 locale 的搜索文档（市场默认
    en-GB）——库里的搜索文档只有 en 口径，商品数据不得依赖请求 locale；
    `locale_code` 只用于响应元信息，`language_code` 只影响楼层标题。
    """

    from catalog.search_services import serialize_search_row

    modules = list(
        ChannelModule.objects.filter(channel_code=channel_code, enabled=True)
        .prefetch_related("items__spu__local_category")
        .order_by("sort_order", "public_id")
    )
    spu_ids = [item.spu_id for module in modules for item in module.items.all()]
    docs = _documents(spu_ids, market=market, locale_code=market.default_locale)
    image_paths = _gallery_paths(spu_ids)
    from catalog.models import Spu

    spus = {spu.pk: spu for spu in Spu.objects.filter(pk__in=spu_ids)}
    slug = channel_root_slug(channel_code)
    href = f"/c/{slug}" if slug else "/s"

    payload = []
    for module in modules:
        products = []
        for item in module.items.all():
            doc = docs.get(item.spu_id)
            spu = spus.get(item.spu_id)
            image_path = image_paths.get(item.spu_id, "")
            if doc is not None:
                products.append(serialize_search_row(doc, image_path=image_path))
            elif spu is not None:
                products.append(_fallback_product(spu, image_path))
        payload.append(
            {
                "public_id": str(module.public_id),
                "title": _localized_title(module, language_code),
                "title_en": module.title_en,
                "title_zh": module.title_zh,
                "sort_order": module.sort_order,
                "href": href,
                "products": products,
            }
        )
    return {
        "channel_code": channel_code,
        "category_slug": slug,
        "locale": locale_code,
        "modules": payload,
    }


def serialize_admin_module(module: ChannelModule) -> dict:
    return {
        "id": str(module.public_id),
        "channel_code": module.channel_code,
        "title_en": module.title_en,
        "title_zh": module.title_zh,
        "sort_order": module.sort_order,
        "enabled": module.enabled,
        "products": [
            {
                "spu_public_id": str(item.spu.public_id),
                "source_title": item.spu.translations.first().title
                if item.spu.translations.exists()
                else "",
                "sort_order": item.sort_order,
            }
            for item in module.items.select_related("spu").prefetch_related("spu__translations")
        ],
        "updated_at": module.updated_at.isoformat(),
    }


def list_modules(channel_code: str = "") -> list[ChannelModule]:
    rows = ChannelModule.objects.all()
    if channel_code:
        rows = rows.filter(channel_code=channel_code)
    return list(rows.order_by("channel_code", "sort_order", "public_id"))


def _clean_title(value, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ChannelModuleError("FIELD_REQUIRED", f"{field}不能为空。")
    if len(text) > MAX_TITLE_LENGTH:
        raise ChannelModuleError("FIELD_TOO_LONG", f"{field}不能超过 {MAX_TITLE_LENGTH} 个字符。")
    return text


def _clean_sort(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ChannelModuleError("SORT_INVALID", "排序必须是非负整数。") from None
    if number < 0 or number > MAX_SORT_ORDER:
        raise ChannelModuleError("SORT_INVALID", f"排序必须是 0–{MAX_SORT_ORDER} 的整数。")
    return number


def update_module(public_id, payload: dict) -> ChannelModule:
    """更新楼层标题/排序/开关与商品清单（按 SPU public_id 顺序替换）。"""

    from catalog.models import Spu

    module = ChannelModule.objects.filter(public_id=public_id).first()
    if module is None:
        raise ChannelModuleError("MODULE_NOT_FOUND", "频道楼层不存在。", 404)
    payload = payload or {}
    title_en = _clean_title(payload.get("title_en"), field="英文标题")
    title_zh = str(payload.get("title_zh") or "").strip()
    if len(title_zh) > MAX_TITLE_LENGTH:
        raise ChannelModuleError("FIELD_TOO_LONG", f"中文标题不能超过 {MAX_TITLE_LENGTH} 个字符。")
    sort_order = _clean_sort(payload.get("sort_order", module.sort_order))
    enabled = bool(payload.get("enabled", module.enabled))
    product_ids = payload.get("product_public_ids")
    if product_ids is None:
        product_ids = [
            str(item.spu.public_id)
            for item in module.items.select_related("spu").order_by("sort_order")
        ]
    if not isinstance(product_ids, list):
        raise ChannelModuleError("PRODUCTS_INVALID", "商品清单必须是数组。")
    if len(product_ids) > MAX_PRODUCTS:
        raise ChannelModuleError("PRODUCTS_TOO_MANY", f"单个楼层商品不能超过 {MAX_PRODUCTS} 个。")
    product_ids = [str(value).strip() for value in product_ids if str(value or "").strip()]
    if len(set(product_ids)) != len(product_ids):
        raise ChannelModuleError("PRODUCTS_DUPLICATED", "商品清单存在重复商品。")
    spus = {str(spu.public_id): spu for spu in Spu.objects.filter(public_id__in=product_ids)}
    missing = [value for value in product_ids if value not in spus]
    if missing:
        raise ChannelModuleError("PRODUCT_NOT_FOUND", "商品清单包含不存在的商品。")

    with transaction.atomic():
        module.title_en = title_en
        module.title_zh = title_zh
        module.sort_order = sort_order
        module.enabled = enabled
        module.save(update_fields=["title_en", "title_zh", "sort_order", "enabled", "updated_at"])
        module.items.all().delete()
        ChannelModuleProduct.objects.bulk_create(
            [
                ChannelModuleProduct(module=module, spu=spus[value], sort_order=index)
                for index, value in enumerate(product_ids)
            ]
        )
    return module
