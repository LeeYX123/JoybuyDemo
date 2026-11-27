"""购物端公开商家接口（WP-42，文档「三、购物端 → 搜索结果页（搜商家）」）。

原站 joybuy.co.uk 不支持搜商家，这是本项目新增页面：
- ``GET /api/v1/merchants/search?q=``  按商家店铺名称匹配（不做 ID 搜索）；
- ``GET /api/v1/merchants/<slug>/``    商家主页头 + 该店当前上架的全部商品。

两个接口都只读、无需登录；总关注/总曝光度为**总数**（不是今日）。
"""

from catalog.models import Sku, Spu
from django.db.models import Exists, OuterRef, Q
from django.http import JsonResponse
from offers.models import Offer

# 商家页商品卡兜底图（本地资源，storefront/public/images/categories/）。
# 需求 20.2：不得返回空字符串，否则前端 <img v-if> 不渲染形成白块。
PRODUCT_PLACEHOLDER_IMAGE = "/images/categories/_placeholder.svg"


def _merchant_header(merchant) -> dict:
    return {
        "id": str(merchant.public_id),
        "slug": merchant.slug,
        "name": merchant.display_name,
        "avatar": merchant.avatar_url,
        "followers_total": merchant.followers,
        "exposure_total": merchant.exposure,
        "status": merchant.onboarding_status,
    }


def _media_file_exists(relative_path: str) -> bool:
    """本地后端必须校验磁盘文件真实存在（S3 时代迁移遗留的 DB 行会指向缺失文件）。

    S3 后端对象存在性以 DB 记录为准，不做逐对象 HEAD（会变成 50 次网络请求）。
    """

    from media.domain import MediaPathInvalid
    from media.storage import resolve_media_path, s3_enabled

    if s3_enabled():
        return True
    try:
        return resolve_media_path(relative_path).is_file()
    except MediaPathInvalid:
        return False


def _gallery_paths(spu_ids) -> dict[int, str]:
    """批量取 SPU 的第一张本地画廊图（role=gallery），一次查询取完。

    商家页一次最多 50 个商品，逐商品查 MediaUsage 会 N+1（需求 20.2）。
    DB 里的 usage 可能指向本地已缺失的文件（S3 时代遗留），必须按磁盘存在性
    过滤，否则会返回 404 路径形成白块；同 SPU 按 sort_order 找下一张存在的。
    """

    if not spu_ids:
        return {}

    from django.contrib.contenttypes.models import ContentType
    from media.models import MediaUsage
    from media.storage import media_url

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
        if usage.object_id in result:
            continue
        if not _media_file_exists(usage.asset.relative_path):
            continue
        result[usage.object_id] = media_url(usage.asset.relative_path)
    return result


def _product_image(spu, gallery_paths: dict[int, str]) -> str:
    """封面回退链：spu.image_urls[0] → 本地画廊首图 → 本地占位图。"""

    image_urls = spu.image_urls if isinstance(spu.image_urls, list) else []
    if image_urls and image_urls[0]:
        return str(image_urls[0])
    return gallery_paths.get(spu.pk) or PRODUCT_PLACEHOLDER_IMAGE


def _product_payload(offer: Offer, *, image: str, family=None, stats=None) -> dict:
    spu = offer.sku.spu
    translation = (
        spu.translations.filter(locale__in=["zh-CN", "zh", "en-GB", "en"]).order_by("pk").first()
        or spu.translations.order_by("pk").first()
    )
    stats = stats or {}
    return {
        "product_id": str(spu.public_id),
        "offer_id": str(offer.public_id),
        "name": translation.title if translation else "",
        "image": image,
        "price": str(offer.current_price),
        "currency": offer.currency.code,
        "merchant_category": spu.merchant_category,
        "merchant_category_label": Spu.merchant_category_label(spu.merchant_category),
        # 评分/已售快照（ADR-0003）：商家页显示评分已售行，但无自营徽标。
        "rating_average": stats.get("rating_average"),
        "rating_count": stats.get("rating_count", 0),
        "sold_amount": stats.get("sold_amount"),
        # 批次 DB（2026-11-27）：族信息只做增量字段，老前端忽略也不影响。
        "family_key": family["family_key"] if family else "",
        "family_representative_public_id": str(family["representative_public_id"]) if family else "",
    }


def _family_map(spu_ids):
    """SPU → {family_key, family_id, representative_spu_id/public_id}（一次查询）。"""

    from catalog.models import VariantFamilyMember

    rows = (
        VariantFamilyMember.objects.filter(spu_id__in=set(spu_ids))
        .values(
            "spu_id",
            "family_id",
            "family__family_key",
            "family__representative_spu_id",
            "family__representative_spu__public_id",
        )
        .distinct()
    )
    result = {}
    for row in rows:
        result.setdefault(
            row["spu_id"],
            {
                "family_id": row["family_id"],
                "family_key": row["family__family_key"],
                "representative_spu_id": row["family__representative_spu_id"],
                "representative_public_id": row["family__representative_spu__public_id"],
            },
        )
    return result


def _dedupe_by_family(offers, family_by_spu, *, limit=50):
    """同款族只留一张卡（Q7）：优先保留「代表 SPU 的 offer」，否则取最便宜的一张。

    商家页是「这个商家卖什么」，所以卡片的 ``product_id``/``offer_id`` 指向真实
    在售的那个 offer（可能落在族内非代表 SPU 上）；点击进 PDP 时带 ``?offer=``，
    PDP 会默认选中该商家的 offer（Q10）。

    单遍扫描全部 offer（按 ``-listed_at`` 顺序 = 最新上架在前），族首次出现即占位，
    后续同族 offer 只做「代表优先 / 更便宜」的替换；攒够 ``limit`` 个族就提前结束。
    """

    picks = {}  # key -> (offer, family)
    order = []
    for offer in offers:
        spu_id = offer.sku.spu_id
        family = family_by_spu.get(spu_id)
        key = ("family", family["family_id"]) if family else ("spu", spu_id)
        current = picks.get(key)
        if current is None:
            picks[key] = (offer, family)
            order.append(key)
            if len(order) >= limit:
                break
            continue
        existing_offer, _family = current
        existing_rep = family is not None and existing_offer.sku.spu_id == family["representative_spu_id"]
        candidate_rep = family is not None and spu_id == family["representative_spu_id"]
        if candidate_rep and not existing_rep:
            picks[key] = (offer, family)
        elif candidate_rep == existing_rep and offer.current_price < existing_offer.current_price:
            picks[key] = (offer, family)
    return [picks[key] for key in order]


def _listed_offers(merchant):
    """商家页可售商品：Offer ACTIVE + SKU ACTIVE + SPU ACTIVE（与 PDP 可点入口径一致）。"""

    return (
        Offer.objects.filter(
            merchant=merchant,
            status=Offer.Status.ACTIVE,
            sku__status=Sku.Status.ACTIVE,
            sku__spu__status=Spu.Status.ACTIVE,
        )
        .select_related("sku__spu", "currency")
        .prefetch_related("sku__spu__translations")
        .order_by("-listed_at", "-pk")
    )


def merchant_search(request):
    query = (request.GET.get("q") or "").strip()
    merchants_qs = (
        _searchable_merchants()
        .filter(Q(display_name__icontains=query) | Q(slug__icontains=query))
        .order_by("-followers", "display_name")[:20]
    )
    return JsonResponse(
        {"items": [_merchant_header(merchant) for merchant in merchants_qs]}
    )


def merchant_detail(request, slug):
    merchant = _searchable_merchants().filter(slug=slug).first()
    if merchant is None:
        return JsonResponse(
            {"error": {"code": "MERCHANT_NOT_FOUND", "message": "商家不存在。"}}, status=404
        )
    payload = _merchant_header(merchant)
    # 批次 DB（Q7）：商家页商品按同款族去重——同一族的多个变体 SPU 只出一张卡。
    # 单遍扫描（族内可能有大量变体挂在这个商家上），攒够 50 个族即停。
    offers = _listed_offers(merchant).iterator(chunk_size=500)
    family_by_spu = _family_map(
        Offer.objects.filter(
            merchant=merchant,
            status=Offer.Status.ACTIVE,
            sku__status=Sku.Status.ACTIVE,
            sku__spu__status=Spu.Status.ACTIVE,
        ).values_list("sku__spu_id", flat=True)
    )
    picks = _dedupe_by_family(offers, family_by_spu, limit=50)
    gallery_paths = _gallery_paths(offer.sku.spu_id for offer, _family in picks)
    # 评分/已售（ADR-0003）：一次批量取 SpuDetail 快照。
    from catalog.models import SpuDetail

    detail_stats = {}
    for row in SpuDetail.objects.filter(
        spu_id__in={offer.sku.spu_id for offer, _family in picks}
    ).only("spu_id", "rating_average", "rating_count", "sale_amount"):
        detail_stats[row.spu_id] = {
            "rating_average": str(row.rating_average) if row.rating_average is not None else None,
            "rating_count": row.rating_count or 0,
            "sold_amount": row.sale_amount or None,
        }
    payload["products"] = [
        _product_payload(
            offer,
            image=_product_image(offer.sku.spu, gallery_paths),
            family=family,
            stats=detail_stats.get(offer.sku.spu_id) or {},
        )
        for offer, family in picks
    ]
    return JsonResponse({"merchant": payload})


def _searchable_merchants():
    """可被搜到的商家：排除技术收纳桶与未接单商家，且必须在售至少一件商品。"""

    from merchants.models import Merchant

    has_active_offer = Offer.objects.filter(
        merchant=OuterRef("pk"), status=Offer.Status.ACTIVE
    )
    return (
        Merchant.objects.annotate(listed=Exists(has_active_offer))
        .filter(
            listed=True,
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
        )
        .exclude(merchant_type=Merchant.Type.IMPORT_FALLBACK)
    )
