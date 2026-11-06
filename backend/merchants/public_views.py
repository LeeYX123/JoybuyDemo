"""购物端公开商家接口（WP-42，文档「三、购物端 → 搜索结果页（搜商家）」）。

原站 joybuy.co.uk 不支持搜商家，这是本项目新增页面：
- ``GET /api/v1/merchants/search?q=``  按商家店铺名称匹配（不做 ID 搜索）；
- ``GET /api/v1/merchants/<slug>/``    商家主页头 + 该店当前上架的全部商品。

两个接口都只读、无需登录；总关注/总曝光度为**总数**（不是今日）。
"""

from django.db.models import Exists, OuterRef, Q
from django.http import JsonResponse

from catalog.models import Spu
from offers.models import Offer


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


def _product_payload(offer: Offer) -> dict:
    spu = offer.sku.spu
    translation = (
        spu.translations.filter(locale__in=["zh-CN", "zh", "en-GB", "en"]).order_by("pk").first()
        or spu.translations.order_by("pk").first()
    )
    return {
        "product_id": str(spu.public_id),
        "offer_id": str(offer.public_id),
        "name": translation.title if translation else "",
        "image": spu.image_urls[0] if spu.image_urls else "",
        "price": str(offer.current_price),
        "currency": offer.currency.code,
        "merchant_category": spu.merchant_category,
        "merchant_category_label": Spu.merchant_category_label(spu.merchant_category),
    }


def _listed_offers(merchant):
    return (
        Offer.objects.filter(merchant=merchant, status=Offer.Status.ACTIVE)
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
    payload["products"] = [_product_payload(offer) for offer in _listed_offers(merchant)[:50]]
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
