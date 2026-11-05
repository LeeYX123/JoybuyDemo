"""商家端 M03 商品上架中心。

商品池复用 ``catalog.Spu``（全平台商品），店铺商品关系复用 ``offers.Offer``
（merchant × sku × market × currency）。「上架」只是在本店创建或复活一条 Offer，
并把商品池的成本价/零售价快照过去，不复制商品主档。
"""

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from audit.services import record_audit
from catalog.models import LocalCategory, Spu
from merchant_ops.api_utils import money_str, paginate, require
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.views_catalog import _category_payload, _primary_images, _spu_payload
from offers.models import Market, Offer

# 文档里的「活动商品」不是真实类目，是商品池上的 is_activity 标记。
ACTIVITY_CATEGORY = "ACTIVITY"
# 与商城详情/搜索保持一致：默认市场 GB。
DEFAULT_MARKET_CODE = "GB"


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
    """品类按钮数据源：一级本地类目 +「活动商品」。"""

    permission_any = ("merchant.listings.manage",)

    def get(self, request):
        rows = LocalCategory.objects.filter(status=LocalCategory.Status.ACTIVE, depth=0).order_by(
            "sort_order", "path"
        )[:20]
        items = [
            {
                "id": str(category.public_id),
                "name": category.name_zh or category.name,
                "name_en": category.name_en,
            }
            for category in rows
        ]
        items.append({"id": ACTIVITY_CATEGORY, "name": "活动商品", "name_en": "Activity"})
        return Response({"items": items})


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
                queryset = queryset.filter(local_category__public_id=category)

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
            raise StaffApiError(
                business_code="MERCHANT_NOT_OPERABLE",
                message="当前店铺不是接单中或保证金未缴足，不能上架商品。",
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
        if spu.cost_price is None or spu.retail_price is None:
            raise StaffApiError(
                business_code="PRODUCT_PRICE_MISSING",
                message="商品缺少成本价或零售价，暂不能上架。",
                status_code=400,
            )
        if spu.retail_price < spu.cost_price:
            raise StaffApiError(
                business_code="PRODUCT_PRICE_INVALID",
                message="商品零售价低于成本价，不能上架。",
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
                existing.cost_price = spu.cost_price
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
                    cost_price=spu.cost_price,
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
                    "cost": str(spu.cost_price),
                    "price": str(spu.retail_price),
                },
                tenant_type="MERCHANT",
                tenant_id=str(merchant.public_id),
            )
        images = _primary_images([spu.pk])
        return Response(
            {"listing": _listing_payload(offer, image=images.get(spu.pk, ""))}, status=201
        )
