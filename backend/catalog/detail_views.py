import uuid

from django.db import OperationalError, ProgrammingError
from django.http import JsonResponse

from catalog.localization_services import localized_specification, resolve_product_content
from catalog.models import Sku, Spu, SpuDetailTranslation
from offers.market_services import offer_market_chain, resolve_market_context
from offers.models import Offer
from reviews.models import Review


def _offer_merchant_payload(offer: Offer) -> dict:
    """归属入口用：SKU offer 所属商家（需求 20.3，增量字段不破坏既有契约）。"""

    merchant = offer.merchant
    return {
        "public_id": str(merchant.public_id),
        "display_name": merchant.display_name,
        "slug": merchant.slug,
        "avatar_url": merchant.avatar_url,
    }


def _offer_payload(offer: Offer, *, requested_market, price_source_market) -> dict:
    return {
        "public_id": str(offer.public_id),
        "price": str(offer.current_price),
        "list_price": str(offer.list_price) if offer.list_price is not None else None,
        "promotion_label": offer.promotion_label,
        "currency": offer.currency.code,
        "display_currency_symbol": requested_market.display_currency_symbol,
        "price_source_market": price_source_market.code,
        "inventory_display": offer.display_inventory,
        "source_availability": offer.source_availability,
        "is_purchasable": (
            offer.status == Offer.Status.ACTIVE
            and offer.local_inventory > 0
            and offer.source_availability != Offer.SourceAvailability.UNAVAILABLE
        ),
        "merchant": _offer_merchant_payload(offer),
    }


def _parse_offer_id(value: str):
    """``?offer=`` 是外部 UUID；脏参数按未提供处理（不能 500）。"""

    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _resolve_sku_offer(sku, market, preferred_offer_id):
    """按 market 回退链取 SKU 的 offer；带 ``offer`` 参数时优先该商家的 offer。

    同一 SKU 可被多个商家上架（需求 20.1）：默认 ``.first()`` 会随机落到别的
    商家，从商家店铺页进来时必须选中链接里那个 offer。
    """

    markets = offer_market_chain(market)
    offers = list(
        Offer.objects.filter(
            sku=sku,
            market__in=markets,
            status=Offer.Status.ACTIVE,
        ).select_related("currency", "merchant")
    )
    if preferred_offer_id is not None:
        for offer in offers:
            if offer.public_id == preferred_offer_id:
                return offer, offer.market
    by_market = {}
    for offer in offers:
        by_market.setdefault(offer.market_id, offer)
    for candidate_market in markets:
        if candidate_market.pk in by_market:
            return by_market[candidate_market.pk], candidate_market
    return None, market


def _video_payload(spu) -> list[dict]:
    """Playable local video list (media library URLs, never the source CDN)."""

    from media.storage import media_url

    videos = []
    for row in spu.videos.all():
        videos.append(
            {
                "url": media_url(row.video.relative_path),
                "poster": (media_url(row.poster.relative_path) if row.poster_id else ""),
                "duration_ms": row.duration_ms,
                "duration": (
                    round(row.duration_ms / 1000, 2) if row.duration_ms is not None else None
                ),
                "source_video_id": row.source_video_id,
                "sort_order": row.sort_order,
            }
        )
    return videos


def _spec_options_payload(spu, options) -> list[dict]:
    """Add local SKU public ids so the storefront can drive selection.

    Crawler ``spec_options`` reference source SKU ids; the storefront only
    knows ``Sku.public_id``. Unmapped ids are dropped (the UI still falls
    back to matching ``sku.specification`` by name/value).
    """

    if not isinstance(options, list):
        return []
    from catalog.models import SkuSourceIdentity

    source_to_public = {
        str(source_id): str(public_id)
        for source_id, public_id in SkuSourceIdentity.objects.filter(sku__spu=spu).values_list(
            "source_id", "sku__public_id"
        )
    }
    result = []
    for option in options:
        if not isinstance(option, dict):
            continue
        values = []
        for value in option.get("values") or []:
            if not isinstance(value, dict) or not value.get("value"):
                continue
            values.append(
                {
                    "value": str(value["value"]),
                    "image_url": value.get("image_url") or "",
                    "sku_ids": [
                        source_to_public[source_id]
                        for source_id in value.get("sku_ids") or []
                        if source_id in source_to_public
                    ],
                }
            )
        if values:
            result.append({"name": str(option.get("name") or ""), "values": values})
    return result


def _detail_translation(spu, locale) -> SpuDetailTranslation | None:
    """Read the ``spu_detail_translation`` row for the locale's language.

    The table is created and written by ``translation_agent`` (SQLAlchemy), so
    it only exists where that tool ran (dev MySQL). Test databases and fresh
    environments lack it: any operational/programming failure degrades to the
    source-language detail payload instead of erroring the endpoint.
    """

    try:
        return SpuDetailTranslation.objects.filter(
            spu_id=spu.pk,
            language_code=locale.language_code,
        ).first()
    except (OperationalError, ProgrammingError):
        return None


def _translated_detail_payload(detail, translation) -> dict:
    """Overlay the translated detail fields on the source payload.

    Empty / not-built translated values (``[]``, ``None``, ``""``) keep the
    source data per field, so partial translations never blank out content
    the crawler captured. ``spec_options`` keeps its ``sku_ids`` / ``image_url``
    structure and still flows through ``_spec_options_payload`` for the local
    ``public_id`` mapping.
    """

    payload = {
        "content_sections": detail.content_sections if detail else [],
        "specification_tables": detail.specification_tables if detail else [],
        "specifications": detail.specifications if detail else [],
        "ai_summary": detail.ai_summary if detail else "",
        "ai_summary_title": detail.ai_summary_title if detail else "",
    }
    if detail is None:
        return payload
    if translation is None:
        return payload
    if translation.content_sections:
        payload["content_sections"] = translation.content_sections
    if translation.specification_tables:
        payload["specification_tables"] = translation.specification_tables
    if translation.specifications:
        payload["specifications"] = translation.specifications
    if translation.ai_summary:
        payload["ai_summary"] = translation.ai_summary
    if translation.ai_summary_title:
        payload["ai_summary_title"] = translation.ai_summary_title
    return payload


def product_detail(request, public_id):
    """Localized storefront product detail for the requested market and locale."""

    context = resolve_market_context(request)
    if context is None:
        return JsonResponse(
            {
                "error": {"code": "MARKET_UNAVAILABLE", "message": "Market not configured."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )

    spu = (
        Spu.objects.filter(public_id=public_id, status=Spu.Status.ACTIVE)
        .select_related(
            "brand",
            "local_category",
            "product_category",
            "product_category__parent",
            "detail",
        )
        .prefetch_related(
            "translations",
            "market_contents__locale",
            "market_contents__market",
            "videos__video",
            "videos__poster",
        )
        .first()
    )
    if spu is None:
        return JsonResponse(
            {
                "error": {"code": "PRODUCT_NOT_AVAILABLE", "message": "Product not available."},
                "request_id": getattr(request, "request_id", None),
            },
            status=404,
        )

    market = context.market
    locale = context.locale
    buyer_account = getattr(request, "buyer_account", None)
    if buyer_account is not None:
        from accounts_buyers.activity_views import record_view

        record_view(spu, buyer_account)
    content = resolve_product_content(spu, market, locale)
    preferred_offer_id = _parse_offer_id(request.GET.get("offer"))
    skus = []
    sku_queryset = (
        Sku.objects.filter(spu=spu, status=Sku.Status.ACTIVE)
        .prefetch_related("specification_translations__locale")
        .order_by("pk")
    )
    for sku in sku_queryset:
        offer, price_source_market = _resolve_sku_offer(sku, market, preferred_offer_id)
        display_specification, specification_translated = localized_specification(sku, locale)
        sku_entry = {
            "public_id": str(sku.public_id),
            "specification": display_specification,
            "canonical_specification": sku.specification,
            "specification_locale": locale.code if specification_translated else None,
            "specification_translated": specification_translated,
            "offer": (
                _offer_payload(
                    offer,
                    requested_market=market,
                    price_source_market=price_source_market,
                )
                if offer
                else None
            ),
        }
        skus.append(sku_entry)

    from django.db.models import Avg, Count

    review_stats = Review.objects.filter(spu=spu, status=Review.Status.ACTIVE).aggregate(
        average=Avg("rating"), count=Count("pk")
    )
    review_distribution = {
        str(row["rating"]): row["total"]
        for row in Review.objects.filter(spu=spu, status=Review.Status.ACTIVE)
        .values("rating")
        .annotate(total=Count("pk"))
        if row["rating"]
    }

    gallery = []
    from django.contrib.contenttypes.models import ContentType

    from media.models import MediaUsage

    spu_usages = MediaUsage.objects.filter(
        content_type=ContentType.objects.get_for_model(Spu), object_id=spu.pk
    ).select_related("asset")
    for usage in spu_usages:
        from media.views import asset_urls

        gallery.append(asset_urls(usage.asset))

    category_breadcrumb = []
    node = spu.product_category
    while node is not None and len(category_breadcrumb) < 2:
        category_breadcrumb.append({"id": node.source_id, "name": node.name, "depth": node.depth})
        node = node.parent
    category_breadcrumb.reverse()

    detail = getattr(spu, "detail", None)
    detail_translation = _detail_translation(spu, locale)

    # 评分汇总：本地有 ACTIVE 评价时以本地统计为准；爬虫商品没有本地评价
    # 行，回退到源站快照（SpuDetail.rating_*，2026-11-10）。
    review_summary = {
        "average": str(review_stats["average"]) if review_stats["average"] else None,
        "count": review_stats["count"] or 0,
        "distribution": review_distribution,
        "source": "local",
    }
    if not review_summary["count"] and detail is not None and detail.rating_count:
        review_summary = {
            "average": (str(detail.rating_average) if detail.rating_average is not None else None),
            "count": detail.rating_count,
            "distribution": detail.rating_distribution or {},
            "source": "crawler",
        }

    # 译文命中时按字段替换图文详情/规格参数表/spec_options/AI 摘要（2026-11-17）；
    # 未命中（无译文行、表不存在）与旧行为逐字节一致。顶层加
    # detail_translated / detail_language 让前端可知当前详情区语言。
    translated_fields = _translated_detail_payload(detail, detail_translation)
    translated_options = (
        detail_translation.spec_options
        if detail_translation is not None and detail_translation.spec_options
        else (detail.spec_options if detail else [])
    )
    detail_payload = {
        "content_sections": translated_fields["content_sections"],
        "specification_tables": translated_fields["specification_tables"],
        "specifications": translated_fields["specifications"],
        "spec_options": _spec_options_payload(spu, translated_options),
        "ai_summary": translated_fields["ai_summary"],
        "ai_summary_title": translated_fields["ai_summary_title"],
        "ai_summary_tags": detail.ai_summary_tags if detail else [],
        "detail_translated": detail_translation is not None,
        "detail_language": detail_translation.language_code if detail_translation else None,
    }

    return JsonResponse(
        {
            "public_id": str(spu.public_id),
            "market": market.code,
            "requested_locale": locale.code,
            "content_locale": content.content_locale,
            "content_market": content.content_market,
            "content_origin": content.origin,
            "display_currency_symbol": market.display_currency_symbol,
            "title": content.title,
            "subtitle": content.subtitle,
            "description": content.description,
            "brand": spu.brand.name if spu.brand else None,
            "category_slug": spu.local_category.slug if spu.local_category else None,
            "category_breadcrumb": category_breadcrumb,
            "gallery": gallery,
            "videos": _video_payload(spu),
            "skus": skus,
            **detail_payload,
            "review_summary": review_summary,
        }
    )
