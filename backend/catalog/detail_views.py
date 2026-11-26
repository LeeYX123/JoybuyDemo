import uuid

from django.db import OperationalError, ProgrammingError
from django.http import JsonResponse
from offers.market_services import offer_market_chain, resolve_market_context
from offers.models import Offer
from reviews.models import Review

from catalog.localization_services import localized_specification, resolve_product_content
from catalog.models import Sku, Spu, SpuDetailTranslation


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


def _parse_uuid(value):
    """外部 UUID 参数；脏参数按未提供处理（不能 500）。"""

    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _parse_offer_id(value: str):
    """``?offer=`` 是外部 UUID；脏参数按未提供处理（不能 500）。"""

    return _parse_uuid(value)


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


def _all_offers_by_sku(sku_ids, market) -> dict[int, list[Offer]]:
    """一次取完这些 SKU 在 market 回退链上的全部 ACTIVE offer，按 sku_id 分组。"""

    if not sku_ids:
        return {}
    markets = offer_market_chain(market)
    result = {}
    for offer in (
        Offer.objects.filter(
            sku_id__in=sku_ids,
            market__in=markets,
            status=Offer.Status.ACTIVE,
        )
        .select_related("currency", "merchant")
        .order_by("sku_id", "current_price", "pk")
    ):
        result.setdefault(offer.sku_id, []).append(offer)
    return result


def _variant_family_payload(spu, market, locale) -> dict | None:
    """批次 DB：族内成员（规格 × 商家），供 PDP 规格区跳兄弟商品 + 选商家。

    只对**多 SPU 的族**返回（``kind != merged`` 且成员数 > 1）：合并族的单 SPU
    多 SKU 由批次 DA 的 ``?sku=`` 处理，不需要跳转。返回结构：

    ``{family_key, kind, axis_hint, representative_spu_public_id, is_representative,
       members: [{spu_public_id, title, axis_label, is_current, price_min, price_max,
                  skus: [{sku_public_id, axis_label, offers: [offer…]}]}]}``
    """

    from catalog.models import SpuTranslation, VariantFamilyMember

    membership = (
        VariantFamilyMember.objects.filter(spu_id=spu.pk)
        .values(
            "family_id",
            "family__family_key",
            "family__kind",
            "family__axis_hint",
            "family__representative_spu_id",
            "family__representative_spu__public_id",
        )
        .first()
    )
    if membership is None:
        return None
    member_rows = list(
        VariantFamilyMember.objects.filter(family_id=membership["family_id"])
        .values("spu_id", "spu__public_id", "axis_label", "sort_order")
        .order_by("sort_order", "spu_id")
        .distinct()
    )
    # 去重到 SPU 级（成员行是按 SKU × offer 展开的）
    member_spus = []
    seen_spus = set()
    for row in member_rows:
        if row["spu_id"] in seen_spus:
            continue
        seen_spus.add(row["spu_id"])
        member_spus.append(row)
    if len(member_spus) < 2:
        return None

    from django.db.models import Max, Min

    member_spu_ids = [row["spu_id"] for row in member_spus]
    titles = {}
    for spu_id, code, title in SpuTranslation.objects.filter(
        spu_id__in=member_spu_ids, locale__in=[locale.code, "en-GB"]
    ).values_list("spu_id", "locale", "title"):
        if code == locale.code or spu_id not in titles:
            titles[spu_id] = title
    member_skus = list(
        Sku.objects.filter(spu_id__in=member_spu_ids, status=Sku.Status.ACTIVE)
        .only("pk", "spu_id", "public_id", "specification")
        .order_by("spu_id", "pk")
    )
    display_specs = {}
    for sku in member_skus:
        display_specs[sku.pk], _translated = localized_specification(sku, locale)
    offers_by_sku = _all_offers_by_sku([sku.pk for sku in member_skus], market)
    price_stats = {}
    markets = offer_market_chain(market)
    for row in (
        Offer.objects.filter(
            sku__spu_id__in=member_spu_ids,
            market__in=markets,
            status=Offer.Status.ACTIVE,
        )
        .values("sku__spu_id")
        .annotate(low=Min("current_price"), high=Max("current_price"))
    ):
        price_stats[row["sku__spu_id"]] = row

    skus_by_spu = {}
    for sku in member_skus:
        skus_by_spu.setdefault(sku.spu_id, []).append(sku)

    members = []
    member_titles = [titles.get(row["spu_id"], "") for row in member_spus]
    # 规格按钮标签：标题去掉族内公共词前缀后的残差（"X Max S AI-Powered Exoskeleton, …"
    # → "X Max S AI-Powered Exoskeleton"）；没有可读残差时回退 SKU 规格/标题。
    from catalog.management.commands.merge_variant_spus import common_word_prefix

    prefix_len = len(common_word_prefix([title for title in member_titles if title] or [""]))
    for row, title in zip(member_spus, member_titles):
        spu_id = row["spu_id"]
        stats = price_stats.get(spu_id) or {}
        sku_entries = []
        for sku in skus_by_spu.get(spu_id, []):
            display_specification = display_specs.get(sku.pk) or {}
            sku_entries.append(
                {
                    "sku_public_id": str(sku.public_id),
                    "axis_label": " / ".join(str(value) for value in display_specification.values()),
                    "specification": display_specification,
                    "offers": [
                        _offer_payload(
                            offer,
                            requested_market=market,
                            price_source_market=offer.market,
                        )
                        for offer in offers_by_sku.get(sku.pk, [])
                    ],
                }
            )
        residual = " ".join(title.split()[prefix_len:]).strip() if title else ""
        label = residual.split(",")[0].strip()[:60]
        if not label:
            label = (
                sku_entries[0]["axis_label"]
                if sku_entries and sku_entries[0]["axis_label"]
                else (title[:60] or row["axis_label"])
            )
        members.append(
            {
                "spu_public_id": str(row["spu__public_id"]),
                "title": title,
                "axis_label": label,
                "is_current": spu_id == spu.pk,
                "price_min": str(stats["low"]) if stats.get("low") is not None else None,
                "price_max": str(stats["high"]) if stats.get("high") is not None else None,
                "skus": sku_entries,
            }
        )

    return {
        "family_key": membership["family__family_key"],
        "kind": membership["family__kind"],
        "axis_hint": membership["family__axis_hint"],
        "representative_spu_public_id": str(
            membership["family__representative_spu__public_id"]
        ),
        "is_representative": membership["family__representative_spu_id"] == spu.pk,
        "members": members,
    }


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


def _variant_archive_payload(spu, sku_public_id, locale):
    """``?sku=`` 命中的变体档案（批次 DA）；无档案返回 None。

    既有顶层字段（gallery/title/review_summary/content_sections...）不在这里
    覆盖——前端按 ``share_metadata`` 决定是否采用本块的覆盖值，未采用时页面
    与旧行为逐字段一致。档案缺图（``gallery=[]``）或没有 ``detail`` 时前端
    回退顶层数据，这里不做兜底，避免把「档案缺失」伪装成「切换成功」。
    """

    if sku_public_id is None:
        return None

    from media.models import MediaAsset
    from media.views import asset_urls

    from catalog.models import SpuVariantArchive
    from catalog.variant_archive_services import (
        pick_title,
        rating_snapshot_payload,
    )

    archive = (
        SpuVariantArchive.objects.filter(
            spu=spu,
            sku__public_id=sku_public_id,
            sku__status=Sku.Status.ACTIVE,
        )
        .select_related("sku", "detail_spu", "detail_spu__detail")
        .first()
    )
    if archive is None:
        return None

    gallery = []
    manifest = archive.gallery_manifest if isinstance(archive.gallery_manifest, list) else []
    if manifest:
        assets = {
            asset.relative_path: asset
            for asset in MediaAsset.objects.filter(relative_path__in=manifest)
        }
        for path in manifest:
            asset = assets.get(path)
            if asset is not None:
                gallery.append(asset_urls(asset))

    detail_payload = None
    if archive.detail_spu_id:
        source_detail = getattr(archive.detail_spu, "detail", None)
        translation = _detail_translation(archive.detail_spu, locale)
        fields = _translated_detail_payload(source_detail, translation)
        detail_payload = {
            "content_sections": fields["content_sections"],
            "specification_tables": fields["specification_tables"],
            "specifications": fields["specifications"],
            "ai_summary": fields["ai_summary"],
            "ai_summary_title": fields["ai_summary_title"],
            "ai_summary_tags": source_detail.ai_summary_tags if source_detail else [],
            "detail_translated": translation is not None,
            "detail_language": translation.language_code if translation else None,
        }

    sold_snapshot = archive.sold_snapshot if isinstance(archive.sold_snapshot, dict) else {}
    return {
        "sku": str(archive.sku.public_id),
        "source_spu_public_id": str(archive.source_spu_public_id),
        "axis_label": archive.axis_label,
        "share_metadata": archive.share_metadata,
        "share_metadata_reason": archive.share_metadata_reason,
        "gallery": gallery,
        "review_summary": rating_snapshot_payload(archive.rating_snapshot),
        "sale_amount": sold_snapshot.get("sale_amount") or None,
        "title": pick_title(archive.title_snapshots, locale.code) or None,
        "detail": detail_payload,
    }


def _active_spu_detail_queryset(public_id):
    """PDP 用的单 SPU 读取集合（详情 + 译文 + 市场内容 + 视频）。"""

    return (
        Spu.objects.filter(public_id=public_id, status=Spu.Status.ACTIVE)
        .select_related(
            "brand",
            "local_category",
            "product_category",
            "product_category__parent",
            "product_category__local_category",
            "product_category__parent__local_category",
            "detail",
        )
        .prefetch_related(
            "translations",
            "market_contents__locale",
            "market_contents__market",
            "videos__video",
            "videos__poster",
        )
    )


def product_alias(request, old_public_id):
    """旧商品 id → 保留商品 id 的别名查询（批次 CB2 同款合并）。

    购物端 server middleware 在渲染 ``/p/<old>`` 之前查一次并 301 到保留
    商品；404 表示该 id 不是被合并商品（按普通 PDP 流程继续）。
    """

    from catalog.models import SpuAlias

    alias = SpuAlias.objects.select_related("spu").filter(old_public_id=old_public_id).first()
    if alias is None or alias.spu.status != Spu.Status.ACTIVE:
        return JsonResponse(
            {
                "error": {"code": "ALIAS_NOT_FOUND", "message": "No alias for this product id."},
                "request_id": getattr(request, "request_id", None),
            },
            status=404,
        )
    response = JsonResponse(
        {
            "old_public_id": str(old_public_id),
            "canonical_public_id": str(alias.spu.public_id),
        }
    )
    # 别名在合并且回滚前都不变；短缓存足够挡住热门旧链接的重复查询。
    response["Cache-Control"] = "public, max-age=60"
    return response


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

    from catalog.models import SpuAlias

    spu = _active_spu_detail_queryset(public_id).first()
    canonical_public_id = None
    if spu is None:
        # 别名回退（批次 CB2）：被合并 SPU 的 public_id 归档后仍可读取，返回
        # 保留商品的完整 payload，并带 canonical_public_id 供前端换成新 URL。
        alias = SpuAlias.objects.filter(old_public_id=public_id).first()
        if alias is not None:
            spu = _active_spu_detail_queryset(alias.spu.public_id).first()
            if spu is not None:
                canonical_public_id = str(spu.public_id)
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
    # 批次 DA：``?sku=`` 选中的变体档案（合并后的商品切规格用）。无参数/无档案时
    # 返回 null；顶层字段保持不变，兼容既有购物端与缓存。
    requested_sku_id = _parse_uuid(request.GET.get("sku"))
    skus = []
    sku_queryset = (
        Sku.objects.filter(spu=spu, status=Sku.Status.ACTIVE)
        .prefetch_related("specification_translations__locale")
        .order_by("pk")
    )
    sku_list = list(sku_queryset)
    # 批次 DB（Q9）：每个 SKU 的**全部商家 offer**，供「规格 × 商家」两级选择。
    # 一次性取完，避免逐 SKU 查询（N+1）。
    offers_by_sku = _all_offers_by_sku([sku.pk for sku in sku_list], market)
    for sku in sku_list:
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
            # 该规格的全部商家（含价格/库存/可购性），前端渲染「商家」轴。
            "offers": [
                _offer_payload(
                    candidate,
                    requested_market=market,
                    price_source_market=candidate.market,
                )
                for candidate in offers_by_sku.get(sku.pk, [])
            ],
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

    # 面包屑每级增量返回 ``local_slug``（2026-11-23 批次 A）：来源是
    # ``ProductCategory.local_category`` 的回填映射。前端优先用它拼落地页，
    # 解决「配件」按名称全局匹配误落到 fashion-accessories 的问题；没有映射
    # 时返回 null，前端按「父级 + 名称」回退。
    category_breadcrumb = []
    node = spu.product_category
    while node is not None and len(category_breadcrumb) < 2:
        category_breadcrumb.append(
            {
                "id": node.source_id,
                "name": node.name,
                "depth": node.depth,
                "local_slug": node.local_category.slug if node.local_category_id else None,
            }
        )
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
            # 命中旧 id 别名时返回保留商品 id（批次 CB2）；正常访问为 None。
            "canonical_public_id": canonical_public_id,
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
            "variant_archive": _variant_archive_payload(spu, requested_sku_id, locale),
            # 批次 DB：族内兄弟商品（未合并族跳转 + 规格×商家两级选择）。
            # 合并族（1 SPU 多 SKU）为 null，仍走上面的 ?sku= 档案。
            "variant_family": _variant_family_payload(spu, market, locale),
            **detail_payload,
            "review_summary": review_summary,
            # 需求 22.1-5：PDP 商品名下方「已售 x 件」。源站销量展示值（如
            # "10k+"）由爬虫写入 SpuDetail.sale_amount；无详情行时为 null，
            # 前端只在 null 时使用确定性占位值。
            "sale_amount": (detail.sale_amount or None) if detail is not None else None,
        }
    )
