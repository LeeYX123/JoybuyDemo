"""商家端 M03 商品上架中心。

商品池复用 ``catalog.Spu``（全平台商品），店铺商品关系复用 ``offers.Offer``
（merchant × sku × market × currency）。「上架」只是在本店创建或复活一条 Offer，
并把折扣折算后的成本价/零售价快照过去，不复制商品主档。

WP-42（文档 M03 §2）：零售价 = 抓取到的价格原样保留；成本价按**商家级统一折扣**
计算 = 向上取整(零售价 × 折扣)，活动商品优先用活动折扣。折扣由管理端按商家设置。
"""

from decimal import ROUND_CEILING, Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from audit.services import record_audit
from catalog.models import Spu
from merchant_ops.api_utils import money_str, paginate, require
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.views_catalog import _category_payload, _primary_images, _spu_payload
from offers.models import Market, Offer

# 文档里的「活动商品」不是真实类目，是商品池上的 is_activity 标记。
ACTIVITY_CATEGORY = "ACTIVITY"
# 与商城详情/搜索保持一致：默认市场 GB。
DEFAULT_MARKET_CODE = "GB"


def merchant_category_items() -> list:
    """12 个固定品类 +「活动商品」筛选（活动商品是标记，不改原品类）。"""
    items = [
        {"id": value, "name": label, "name_en": value}
        for value, label in Spu.MerchantCategory.choices
    ]
    items.append({"id": ACTIVITY_CATEGORY, "name": "活动商品", "name_en": "Activity"})
    return items


def compute_listing_cost(merchant, spu):
    """按商家折扣计算上架成本价：向上取整(零售价 × 折扣)，取整到个位。

    取折扣顺序（文档拍板）：先判断活动商品 → 用活动折扣；否则用普通折扣；
    商家未设置折扣时回退商品池建议成本价（保持既有行为）。
    例：12.10 与 12.90 取整后都是 13；121.98 → 122。
    """

    if spu.retail_price is None:
        return spu.cost_price
    rate = None
    if spu.is_activity and merchant.activity_discount_rate is not None:
        rate = merchant.activity_discount_rate
    elif merchant.discount_rate is not None:
        rate = merchant.discount_rate
    if rate is None:
        return spu.cost_price
    factor = (Decimal(str(rate)) / Decimal("100")).quantize(Decimal("0.000001"))
    return (spu.retail_price * factor).to_integral_value(rounding=ROUND_CEILING)


def _default_market() -> Market:
    market = (
        Market.objects.select_related("default_currency")
        .filter(code=DEFAULT_MARKET_CODE, is_active=True)
        .first()
    )
    if market is None:
        raise StaffApiError(
            business_code="MARKET_UNAVAILABLE",
            message="默认市场未配置，暂时无法上架。",
            status_code=400,
        )
    return market


def _listed_spu_ids(merchant) -> set:
    return set(
        Offer.objects.filter(merchant=merchant, status=Offer.Status.ACTIVE).values_list(
            "sku__spu_id", flat=True
        )
    )


def _listing_payload(offer: Offer, *, image: str = "") -> dict:
    spu = offer.sku.spu
    return {
        "offer_id": str(offer.public_id),
        "product_id": str(spu.public_id),
        "name": _spu_title(spu),
        "category": _category_payload(spu.local_category),
        "merchant_category": spu.merchant_category,
        "merchant_category_label": Spu.merchant_category_label(spu.merchant_category),
        "description": spu.description,
        "image": image or (spu.image_urls[0] if spu.image_urls else ""),
        "cost": money_str(offer.cost_price) if offer.cost_price is not None else None,
        "price": money_str(offer.current_price),
        "status": offer.status,
        "listed_at": offer.listed_at.isoformat() if offer.listed_at else None,
        "removed_at": offer.removed_at.isoformat() if offer.removed_at else None,
        "removed_by_platform": offer.removed_by_platform,
        "activity": spu.is_activity,
    }


def _spu_title(spu: Spu) -> str:
    translations = list(spu.translations.all())
    for locale in ("zh-CN", "zh", "en-GB", "en"):
        for translation in translations:
            if translation.locale == locale and translation.title:
                return translation.title
    return translations[0].title if translations else f"SPU {str(spu.public_id)[:8]}"


class MerchantCatalogCategoriesView(MerchantAPIView):
    """品类按钮数据源：12 个固定品类 +「活动商品」（WP-42 文档 M03 §3）。"""

    permission_any = ("merchant.listings.manage",)

    def get(self, request):
        return Response({"items": merchant_category_items()})


class MerchantCatalogProductsView(MerchantAPIView):
    """平台商品池（只读）：按品类/关键词筛选，标注本店是否已上架。"""

    permission_any = ("merchant.listings.manage",)

    def get(self, request):
        merchant = request.merchant
        listed_exists = Offer.objects.filter(
            merchant=merchant,
            sku__spu=OuterRef("pk"),
            status=Offer.Status.ACTIVE,
        )
        queryset = (
            Spu.objects.filter(status=Spu.Status.ACTIVE)
            .select_related("local_category")
            .prefetch_related("translations", "skus")
            .annotate(listed=Exists(listed_exists))
        )

        category = (request.query_params.get("category") or "").strip()
        if category and category.upper() != "ALL":
            if category.upper() == ACTIVITY_CATEGORY:
                queryset = queryset.filter(is_activity=True)
            else:
                queryset = queryset.filter(merchant_category=category)

        query = (request.query_params.get("q") or "").strip()
        if query:
            condition = Q(translations__title__icontains=query) | Q(model_number__icontains=query)
            try:
                import uuid as uuid_module

                condition |= Q(public_id=uuid_module.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition).distinct()

        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request, default_size=8)
        images = _primary_images([spu.pk for spu in rows])
        items = []
        for spu in rows:
            skus = list(spu.skus.all())
            primary_image = images.get(spu.pk)
            payload = _spu_payload(spu, images=[primary_image] if primary_image else [])
            # 商品卡片的成本价按当前商家折扣折算（文档 M03 §2），与上架快照一致。
            discount_cost = compute_listing_cost(merchant, spu)
            payload["cost"] = money_str(discount_cost) if discount_cost is not None else None
            payload["merchant_category"] = spu.merchant_category
            payload["merchant_category_label"] = Spu.merchant_category_label(
                spu.merchant_category
            )
            payload["listed"] = bool(getattr(spu, "listed", False))
            payload["sku_id"] = str(skus[0].public_id) if skus else None
            # 有 SKU 且成本/零售价齐全才允许上架，前端按钮据此置灰；
            # 真正的校验仍在 POST 里做，不能只靠前端禁用。
            payload["can_list"] = bool(
                skus and payload["cost"] is not None and payload["price"] is not None
            )
            items.append(payload)
        return Response({"items": items, **meta})


class MerchantListingsView(MerchantAPIView):
    """本店已上架商品（GET）与上架动作（POST）。"""

    permission_any = ("merchant.listings.manage",)

    def get(self, request):
        queryset = (
            Offer.objects.select_related("sku__spu__local_category")
            .prefetch_related("sku__spu__translations")
            .filter(merchant=request.merchant)
        )
        status = (request.query_params.get("status") or "ACTIVE").upper()
        if status != "ALL":
            queryset = queryset.filter(status=status)
        # 迭代02：平台下架（SPU INACTIVE）后，商家商品中心里也不可见（历史行保留）。
        if status == "ACTIVE":
            queryset = queryset.filter(sku__spu__status=Spu.Status.ACTIVE)
        # M02：支持商品名称与商品 ID 搜索；品类只显示本店已上架商品所属品类。
        query = (request.query_params.get("q") or "").strip()
        if query:
            condition = Q(sku__spu__translations__title__icontains=query)
            try:
                import uuid as uuid_module

                condition |= Q(sku__spu__public_id=uuid_module.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition).distinct()
        category = (request.query_params.get("category") or "").strip()
        if category and category.upper() != "ALL":
            if category.upper() == ACTIVITY_CATEGORY:
                queryset = queryset.filter(sku__spu__is_activity=True)
            else:
                queryset = queryset.filter(sku__spu__merchant_category=category)
        rows, meta = paginate(queryset.order_by("-listed_at", "-pk"), request)
        # 批量取主图，避免逐行查 MediaUsage（列表 20 行就是 20 次查询）。
        images = _primary_images([offer.sku.spu_id for offer in rows])
        return Response(
            {
                "items": [
                    _listing_payload(offer, image=images.get(offer.sku.spu_id, ""))
                    for offer in rows
                ],
                **meta,
            }
        )

    def post(self, request):
        merchant = request.merchant
        payload = request.data or {}
        product_id = require(payload, "product_id", label="商品ID")

        if not merchant.can_operate:
            # 迭代02：未缴保证金给出明确提示，卡在上架流程直到缴纳完成。
            if merchant.deposit_enabled and not merchant.deposit_initial_paid:
                raise StaffApiError(
                    business_code="DEPOSIT_NOT_PAID",
                    message="您当前未缴纳保证金，缴纳完成后才能上架商品。",
                    status_code=400,
                )
            raise StaffApiError(
                business_code="MERCHANT_NOT_OPERABLE",
                message="当前店铺不是接单中，不能上架商品。",
                status_code=400,
            )

        try:
            spu = (
                Spu.objects.select_related("local_category")
                .prefetch_related("skus", "translations")
                .get(public_id=product_id)
            )
        except (Spu.DoesNotExist, ValueError, TypeError) as exc:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND",
                message="商品不存在。",
                status_code=404,
            ) from exc

        if spu.status != Spu.Status.ACTIVE:
            raise StaffApiError(
                business_code="PRODUCT_NOT_AVAILABLE",
                message="该商品已下架，不能上架到店铺。",
                status_code=400,
            )
        if spu.retail_price is None:
            raise StaffApiError(
                business_code="PRODUCT_PRICE_MISSING",
                message="商品缺少零售价，暂不能上架。",
                status_code=400,
            )
        if spu.cost_price is not None and spu.retail_price < spu.cost_price:
            raise StaffApiError(
                business_code="PRODUCT_PRICE_INVALID",
                message="商品零售价低于成本价，不能上架。",
                status_code=400,
            )
        # 成本价 = 向上取整(零售价 × 商家折扣)；未设折扣时回退商品池建议成本价。
        listing_cost = compute_listing_cost(merchant, spu)
        if listing_cost is None:
            raise StaffApiError(
                business_code="PRODUCT_PRICE_MISSING",
                message="商家未设置折扣且商品缺少成本价，暂不能上架。",
                status_code=400,
            )
        sku = spu.skus.filter(status="ACTIVE").order_by("pk").first()
        if sku is None:
            raise StaffApiError(
                business_code="PRODUCT_SKU_MISSING",
                message="该商品没有可售规格，不能上架。",
                status_code=400,
            )

        market = _default_market()
        existing = Offer.objects.filter(
            merchant=merchant, sku=sku, market=market, currency=market.default_currency
        ).first()
        if existing and existing.status == Offer.Status.ACTIVE:
            raise StaffApiError(
                business_code="PRODUCT_ALREADY_LISTED",
                message="该商品已在本店上架，不能重复上架。",
                status_code=409,
            )

        with transaction.atomic():
            if existing:
                # 平台下架后再上架：复用原关系，保留历史流水，不新建一行。
                existing.status = Offer.Status.ACTIVE
                existing.removed_at = None
                existing.removed_by_platform = False
                existing.listed_at = timezone.now()
                existing.cost_price = listing_cost
                existing.current_price = spu.retail_price
                existing.save(
                    update_fields=[
                        "status",
                        "removed_at",
                        "removed_by_platform",
                        "listed_at",
                        "cost_price",
                        "current_price",
                        "updated_at",
                    ]
                )
                offer = existing
            else:
                offer = Offer.objects.create(
                    merchant=merchant,
                    sku=sku,
                    market=market,
                    currency=market.default_currency,
                    current_price=spu.retail_price,
                    list_price=spu.retail_price,
                    cost_price=listing_cost,
                    local_inventory=999,
                    source_availability=Offer.SourceAvailability.IN_STOCK,
                    status=Offer.Status.ACTIVE,
                    listed_at=timezone.now(),
                )
            record_audit(
                request=request,
                actor=request.staff_account,
                action="MERCHANT_PRODUCT_LISTED",
                target_type="offer",
                target_id=str(offer.public_id),
                reason="",
                before_state={},
                after_state={
                    "merchant": str(merchant.public_id),
                    "product": str(spu.public_id),
                    "cost": str(listing_cost),
                    "price": str(spu.retail_price),
                },
                tenant_type="MERCHANT",
                tenant_id=str(merchant.public_id),
            )
        images = _primary_images([spu.pk])
        return Response(
            {"listing": _listing_payload(offer, image=images.get(spu.pk, ""))}, status=201
        )
