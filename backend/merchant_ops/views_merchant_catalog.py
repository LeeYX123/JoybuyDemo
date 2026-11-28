"""商家端 M03 商品上架中心。

商品池复用 ``catalog.Spu``（全平台商品），店铺商品关系复用 ``offers.Offer``
（merchant × sku × market × currency）。「上架」只是在本店创建或复活一条 Offer，
并把折扣折算后的成本价/零售价快照过去，不复制商品主档。

WP-42（文档 M03 §2，2026-11-10 最终口径）：零售价 = 抓取到的价格原样保留；
成本价按**商家级统一折扣**计算 = 零售价 × (1 - 折扣%)，向上取整到分——折扣是
管理端设置的减免百分比，不改变顾客价；未设置折扣视为减免 0%（成本价 = 零售价）；
活动商品优先用活动折扣。折扣由管理端按商家设置（取代 2026-11-08 的
「平台成本价 × (1 - 折扣%)」口径）。
"""

from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from audit.services import record_audit
from catalog.detail_views import _spec_options_payload
from catalog.models import Spu, SpuTranslation
from merchant_ops.api_utils import money_str, paginate, require
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.services import compute_listing_cost
from merchant_ops.views_catalog import (
    _category_payload,
    _detail_summary,
    _primary_images,
    _spu_payload,
)
from offers.models import Market, Offer

__all__ = ["compute_listing_cost"]

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

    # 列表只取页面真正用到的列（2026-11-28 性能优化）：不再整行 SELECT spu，
    # 也不 preload 翻译的 description 长文本。
    list_fields = (
        "id",
        "public_id",
        "local_category_id",
        "status",
        "cost_price",
        "retail_price",
        "is_activity",
        "merchant_category",
        "description",
        "image_urls",
        "specs",
        "created_at",
        "local_category__public_id",
        "local_category__name",
        "local_category__name_zh",
        "local_category__name_en",
        "local_category__path",
    )

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
            .prefetch_related(
                Prefetch(
                    "translations",
                    queryset=SpuTranslation.objects.only("spu_id", "locale", "title"),
                    to_attr="list_translations",
                ),
                "skus",
            )
            .only(*self.list_fields)
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
            # 2026-11-28：标题匹配改子查询，不再 JOIN translations + DISTINCT。
            # 原写法要无条件 ``.distinct()`` 去重，COUNT 变成
            # ``SELECT COUNT(*) FROM (SELECT DISTINCT 全列 … JOIN …)``——prod 实测
            # q=coffee 353ms、q=co 492ms（8,151 命中）。子查询不产生重复行。
            condition = Q(
                pk__in=SpuTranslation.objects.filter(title__icontains=query).values("spu_id")
            ) | Q(model_number__icontains=query)
            try:
                import uuid as uuid_module

                condition |= Q(public_id=uuid_module.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition)

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


class MerchantCatalogProductDetailView(MerchantAPIView):
    """商品池单品详情（只读），供商家端「查看详情」抽屉渲染。

    列表接口 ``MerchantCatalogProductsView`` 只带轻量字段（``description`` /
    ``specs`` 是历史兜底字段，爬虫商品通常为空）。图文详情与规格真数据在
    ``SpuDetail``（content_sections / specification_tables / specifications /
    spec_options）以及 SKU 的 ``specification`` 上，这里增量带上，**不改既有字段**，
    旧消费方可忽略新字段。
    """

    permission_any = ("merchant.listings.manage",)

    def get(self, request, public_id):
        spu = (
            Spu.objects.select_related("local_category", "detail")
            .prefetch_related("translations", "skus")
            .filter(public_id=public_id, status=Spu.Status.ACTIVE)
            .first()
        )
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND",
                message="商品不存在或已下架。",
                status_code=404,
            )
        detail = getattr(spu, "detail", None)
        images = _primary_images([spu.pk])
        payload = _spu_payload(
            spu,
            images=[images[spu.pk]] if spu.pk in images else [],
            detail_summary=_detail_summary(detail),
        )
        # 成本价与列表口径一致：按本店当前折扣折算（上架时快照同一公式）。
        discount_cost = compute_listing_cost(request.merchant, spu)
        payload["cost"] = money_str(discount_cost) if discount_cost is not None else None
        payload["listed"] = Offer.objects.filter(
            merchant=request.merchant,
            sku__spu=spu,
            status=Offer.Status.ACTIVE,
        ).exists()
        skus = list(spu.skus.all())
        payload["sku_count"] = len(skus)
        payload["skus"] = [
            {
                "id": str(sku.public_id),
                "specification": sku.specification or {},
                "status": sku.status,
            }
            for sku in skus[:50]
        ]

        # --- 爬虫详情增量字段（与平台管理端池子详情同名，只读展示）---
        payload["content_sections"] = detail.content_sections if detail else []
        payload["content_source"] = detail.content_source if detail else None
        payload["specification_tables"] = detail.specification_tables if detail else []
        payload["specifications"] = detail.specifications if detail else []
        payload["spec_options"] = _spec_options_payload(spu, detail.spec_options if detail else [])
        payload["ai_summary"] = detail.ai_summary if detail else ""
        payload["ai_summary_title"] = detail.ai_summary_title if detail else ""
        payload["ai_summary_tags"] = detail.ai_summary_tags if detail else []
        return Response({"product": payload})


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
            # 2026-11-28：改子查询，不再 JOIN sku__spu__translations + DISTINCT。
            # 原写法 COUNT 退化成 ``SELECT COUNT(*) FROM (SELECT DISTINCT offer 全列 …)``。
            condition = Q(
                sku__spu_id__in=SpuTranslation.objects.filter(
                    title__icontains=query
                ).values("spu_id")
            )
            try:
                import uuid as uuid_module

                condition |= Q(sku__spu__public_id=uuid_module.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition)
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
        # 成本价 = 向上取整(零售价 × (1 − 商家折扣%))；未设置折扣 = 零售价。
        # 商品池 cost_price 不参与公式，retail_price 为 None 时才返回 None
        # （上面已拦截），此分支只是防御。
        listing_cost = compute_listing_cost(merchant, spu)
        if listing_cost is None:
            raise StaffApiError(
                business_code="PRODUCT_PRICE_MISSING",
                message="商品缺少零售价，暂不能上架。",
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
        # 上架（含平台下架后重新上架）必须刷新搜索文档：商品池新建的商品
        # 在上架前没有任何文档，不刷新就永远搜不到、类目页也不显示。
        from catalog.search_services import refresh_spu_search_documents

        refresh_spu_search_documents(spu)
        images = _primary_images([spu.pk])
        return Response(
            {"listing": _listing_payload(offer, image=images.get(spu.pk, ""))}, status=201
        )
