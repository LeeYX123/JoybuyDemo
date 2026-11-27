"""频道页商品楼层（批次 H，2026-11-19）：公开读取 + 管理端配置。

楼层引用真实 SPU（``ChannelModuleProduct``），购物端按频道取 enabled 楼层，
商品序列化与 ``/api/v1/search`` 同构（``serialize_search_row``），保证
``ProductCard`` 直接复用。管理端接口只允许改标题/排序/开关/商品清单，
不创建或修改商品本身。
"""

from decimal import Decimal

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
        ).select_related("spu", "spu__detail", "local_category")
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
    detail = getattr(spu, "detail", None)
    rating_average = str(detail.rating_average) if detail and detail.rating_average is not None else None
    rating_count = detail.rating_count if detail else 0
    return {
        "spu_public_id": str(spu.public_id),
        "title": translation.title if translation else "",
        "brand": offer.merchant.display_name if offer and offer.merchant_id else "",
        "category_slug": spu.local_category.slug if spu.local_category_id else None,
        "price_min": price,
        "price_max": price,
        "currency": offer.currency.code if offer and offer.currency_id else None,
        "rating_average": rating_average,
        "rating_count": rating_count or 0,
        "sold_amount": (detail.sale_amount or None) if detail else None,
        "image_path": image_path,
    }


def _retail_price(spu) -> str | None:
    """后台零售价（``Spu.retail_price``）：4 位小数字符串或 null。

    与 ``price_min`` / ``price_max`` 同一字符串口径，实现复用
    ``catalog.search_services.retail_price_text``（与搜索/推荐同一份逻辑）。
    """

    from catalog.search_services import retail_price_text

    return retail_price_text(spu)


_PRICE_QUANTUM = Decimal("0.0001")


def _price_value(value) -> Decimal | None:
    """报价/零售价规整到同一精度（4 位小数）后再比较，避免精度差误判。"""

    if value is None:
        return None
    return Decimal(value).quantize(_PRICE_QUANTUM)


def _spu_sku_prices(spu_ids, *, market) -> dict[int, dict[int, Decimal]]:
    """同批 SPU 的 ``{spu_id: {sku_id: 该 SKU 的 ACTIVE 报价最低价}}``（一次查询）。

    供 ``retail_price`` 归属判据使用：要判断「零售价是不是兄弟尺码的价」，需要
    同 SPU 其它可售 SKU 的报价。必须整批取，不能在楼层 item 循环里逐条查库
    （禁止 N+1）。市场口径与 ``_sku_offers`` 一致：优先请求市场的报价，该 SKU
    在请求市场没有 ACTIVE 报价时回退到任意市场的最低价。
    """

    from catalog.models import Sku
    from offers.models import Offer

    if not spu_ids:
        return {}
    rows = Offer.objects.filter(
        sku__spu_id__in=set(spu_ids),
        sku__status=Sku.Status.ACTIVE,
        status=Offer.Status.ACTIVE,
    ).values_list("sku__spu_id", "sku_id", "market_id", "current_price")
    primary: dict[int, dict[int, Decimal]] = {}
    fallback: dict[int, dict[int, Decimal]] = {}
    for spu_id, sku_id, market_id, price in rows:
        bucket = (primary if market_id == market.pk else fallback).setdefault(spu_id, {})
        value = _price_value(price)
        current = bucket.get(sku_id)
        if current is None or value < current:
            bucket[sku_id] = value
    result: dict[int, dict[int, Decimal]] = {}
    for source in (fallback, primary):
        for spu_id, prices in source.items():
            result.setdefault(spu_id, {}).update(prices)
    return result


def _output_retail_price(spu, *, sku_id, card_price, spu_sku_prices) -> str | None:
    """楼层卡输出的 ``retail_price``：先把「零售价是否属于这张卡自己的尺码」判掉。

    ``Spu.retail_price`` 是 SPU 级的后台零售价（原价），但一个 SPU 会聚合差异
    很大的变体（30 包 vs 4 包、1 听 vs 24 听），零售价可能来自另一个尺码。此时
    输出 null，让前端回退到该卡自己的 ``price_min``（不做折扣换算）。

    置 null 的三种情况（逐卡计算）：

    * 零售价为空；
    * ``retail < card_price``——零售价低于该卡自己的报价，说明它属于更便宜的变体；
    * 同 SPU 有另一个可售 SKU 的 ACTIVE 报价恰好等于 ``retail``，且该卡自己的
      报价不等于 ``retail``——零售价正好是兄弟尺码的价。

    否则照常输出（保留「原价 > 折后价」的正确场景，如 21.99 原价 / 3.97 折后）。
    """

    retail = _retail_price(spu)
    if spu is None or spu.retail_price is None or retail is None:
        return None
    retail_value = _price_value(spu.retail_price)
    card_value = _price_value(card_price)
    if card_value is not None and retail_value < card_value:
        return None
    if card_value == retail_value:
        return retail
    siblings = spu_sku_prices.get(spu.pk, {})
    if any(price == retail_value for other_id, price in siblings.items() if other_id != sku_id):
        return None
    return retail


def _sku_variant_images(sku_ids) -> dict[int, str]:
    """第一张 SKU 变体图（``MediaUsage(role="variant")``），按 sku_id 取首张。

    导入链路把变体规格图挂在 SKU 上（``crawler_control.import_services``），
    楼层卡按 SKU 展示时优先用它，没有则回退 SPU gallery 首图。
    """

    from django.contrib.contenttypes.models import ContentType

    from catalog.models import Sku
    from media.models import MediaUsage
    from media.storage import media_url

    if not sku_ids:
        return {}
    sku_type = ContentType.objects.get_for_model(Sku)
    usages = (
        MediaUsage.objects.filter(
            content_type=sku_type,
            object_id__in=set(sku_ids),
            role="variant",
        )
        .select_related("asset")
        .order_by("object_id", "sort_order", "pk")
    )
    result = {}
    for usage in usages:
        result.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return result


def _sku_offers(sku_ids, *, market) -> dict:
    """每个 SKU 一条 ACTIVE 报价（一次查询，避免循环里逐条查 Offer）。

    优先请求市场（GB）的报价，该 SKU 在请求市场没有报价时回退到任意市场的
    最低价——与 ``_fallback_product`` 的「不让卡片空白」一致。
    """

    from offers.models import Offer

    if not sku_ids:
        return {}
    rows = (
        Offer.objects.filter(sku_id__in=set(sku_ids), status=Offer.Status.ACTIVE)
        .select_related("currency")
        .order_by("sku_id", "current_price", "pk")
    )
    result: dict[int, object] = {}
    fallback: dict[int, object] = {}
    for offer in rows:
        if offer.market_id == market.pk:
            result.setdefault(offer.sku_id, offer)
        else:
            fallback.setdefault(offer.sku_id, offer)
    for sku_id, offer in fallback.items():
        result.setdefault(sku_id, offer)
    return result


def _apply_sku(product: dict, sku, offer) -> None:
    """把商品 item 覆盖成 SKU 口径：价格/图取该 SKU，标题/品牌/零售价仍取 SPU。

    * ``price_min`` / ``price_max`` / ``currency`` 用该 SKU 自己的 ACTIVE 报价
      （口径与搜索 item 一致：4 位小数字符串）。该 SKU 没有 ACTIVE 报价时保留
      文档/兜底价格，不让卡片空白。
    * 图片由调用方传入已解析好的 ``image_path``（变体图优先、SPU gallery 兜底）。
    * 新增 ``sku_public_id`` 与 ``specification``；不改任何既有字段名/语义。
    """

    product["sku_public_id"] = str(sku.public_id)
    product["specification"] = sku.specification if sku.specification else {}
    if offer is None:
        return
    price = str(offer.current_price)
    product["price_min"] = price
    product["price_max"] = price
    product["currency"] = offer.currency.code if offer.currency_id else None


def public_modules(channel_code: str, *, market, locale_code: str, language_code: str) -> dict:
    """购物端频道页楼层：enabled 楼层 + 有序商品（与搜索 item 同构）。

    商品数据（标题/价格/图片）统一取默认 locale 的搜索文档（市场默认
    en-GB）——库里的搜索文档只有 en 口径，商品数据不得依赖请求 locale；
    `locale_code` 只用于响应元信息，`language_code` 只影响楼层标题。
    每个商品额外带 ``retail_price``（后台零售价，4 位小数字符串或 null）。

    2026-11-24「按 SKU 唯一」：位次带 ``sku`` 时按该 SKU 序列化——价格取该
    SKU 的 ACTIVE 报价、图片优先 SKU 变体图（无则 SPU gallery 首图）、标题/
    品牌/``retail_price`` 仍取 SPU，并新增 ``sku_public_id`` / ``specification``。
    位次 ``sku`` 为 NULL（老数据 / 源站解析不到 SKU）时与旧版完全一致，两个新
    字段为 null。SKU 的报价与变体图都按批查询（无 N+1）。

    2026-11-24（零售价归属判据）：按 SKU 展开的卡不再无条件带 ``retail_price``
    ——零售价若属于兄弟尺码（低于本卡报价，或恰好等于同 SPU 另一个可售 SKU 的
    报价），该卡输出 null，前端回退 ``price_min``。判定用的兄弟报价整批查询一次。
    """

    from catalog.search_services import serialize_search_row

    modules = list(
        ChannelModule.objects.filter(channel_code=channel_code, enabled=True)
        .prefetch_related("items__spu__local_category", "items__sku")
        .order_by("sort_order", "public_id")
    )
    all_items = [item for module in modules for item in module.items.all()]
    spu_ids = [item.spu_id for item in all_items]
    sku_ids = [item.sku_id for item in all_items if item.sku_id is not None]
    docs = _documents(spu_ids, market=market, locale_code=market.default_locale)
    image_paths = _gallery_paths(spu_ids)
    variant_images = _sku_variant_images(sku_ids)
    sku_offers = _sku_offers(sku_ids, market=market)
    spu_sku_prices = _spu_sku_prices(spu_ids, market=market)
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
            if item.sku_id is not None:
                image_path = variant_images.get(item.sku_id) or image_path
            if doc is not None:
                product = serialize_search_row(doc, image_path=image_path)
            elif spu is not None:
                product = _fallback_product(spu, image_path)
            else:
                continue
            product["retail_price"] = _retail_price(spu)
            if item.sku_id is not None and item.sku is not None:
                offer = sku_offers.get(item.sku_id)
                _apply_sku(product, item.sku, offer)
                # 归属判据只作用于按 SKU 展开的卡（sku=NULL 的老位次保持旧行为）。
                product["retail_price"] = _output_retail_price(
                    spu,
                    sku_id=item.sku_id,
                    card_price=offer.current_price if offer is not None else None,
                    spu_sku_prices=spu_sku_prices,
                )
            else:
                product["sku_public_id"] = None
                product["specification"] = None
            products.append(product)
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
    """更新楼层标题/排序/开关与商品清单（按 SPU public_id 顺序替换）。

    2026-11-24 起位次可能是按 SKU 展开的（同一 SPU 多行）。管理端仍按 SPU 提交
    清单（``product_public_ids``）：重排时把该 SPU 原有的 SKU 明细按原相对顺序
    跟着它走，只删掉被移出清单的 SPU——不会把尺码展开悄悄压回一张卡。
    """

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
        # 楼层位次可能是按 SKU 展开的（同一 SPU 多行），回填时按 SPU 保序去重，
        # 否则会被下面的「重复商品」校验拦掉，管理端连标题都存不回去。
        derived: list[str] = []
        seen_spus: set[str] = set()
        for item in module.items.select_related("spu").order_by("sort_order", "pk"):
            public_id = str(item.spu.public_id)
            if public_id in seen_spus:
                continue
            seen_spus.add(public_id)
            derived.append(public_id)
        product_ids = derived
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
        existing_skus: dict[int, list[int | None]] = {}
        for spu_id, sku_id in module.items.order_by("sort_order", "pk").values_list(
            "spu_id", "sku_id"
        ):
            existing_skus.setdefault(spu_id, []).append(sku_id)
        for spu_id, variants in existing_skus.items():
            # 同一 SPU 既有 SKU 明细又有 SPU 级旧行时，只保留 SKU 明细（旧行是
            # 同一商品的重复卡；同步命令重建后不会出现这种混合，这里做防御）。
            if any(variant is not None for variant in variants):
                existing_skus[spu_id] = [variant for variant in variants if variant is not None]
        module.items.all().delete()
        rows: list[ChannelModuleProduct] = []
        for value in product_ids:
            spu = spus[value]
            # 该 SPU 原有的 SKU 明细（没有则是 SPU 级单条）。
            for sku_id in existing_skus.get(spu.pk) or [None]:
                rows.append(
                    ChannelModuleProduct(
                        module=module,
                        spu=spu,
                        sku_id=sku_id,
                        sort_order=len(rows),
                    )
                )
        ChannelModuleProduct.objects.bulk_create(rows)
    return module
