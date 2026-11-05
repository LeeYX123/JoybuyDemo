"""A03 商品池管理 / A04 商家商品管理。

商品池复用 ``catalog.Spu``（爬虫导入、商城详情、搜索都基于它），
店铺商品关系复用 ``offers.Offer``（merchant × sku × market），
两边都不新建并行表，避免同一件商品有两套主档。
"""

import uuid

from django.db.models import Count, Q
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from catalog.models import LocalCategory, Spu, SpuTranslation
from media.models import MediaUsage
from media.storage import media_url
from merchant_ops.api_utils import (
    OpsAPIView,
    iso,
    money_str,
    paginate,
    parse_amount,
    require,
)
from offers.models import Offer

MAX_IMAGES = 5


def _category_payload(category: LocalCategory | None) -> dict | None:
    if category is None:
        return None
    return {
        "id": str(category.public_id),
        "name": category.name,
        "name_zh": category.name_zh,
        "name_en": category.name_en,
        "path": category.path,
    }


def _primary_images(spu_ids) -> dict:
    """批量取商品主图：优先主图角色，其次任意排序最小的图片。"""

    if not spu_ids:
        return {}
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(Spu)
    usages = (
        MediaUsage.objects.select_related("asset")
        .filter(content_type=content_type, object_id__in=spu_ids)
        .order_by("object_id", "sort_order", "pk")
    )
    result = {}
    for usage in usages:
        result.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return result


def _title_for(spu: Spu) -> str:
    translations = list(spu.translations.all())
    for locale in ("zh-CN", "zh", "en-GB", "en"):
        for translation in translations:
            if translation.locale == locale and translation.title:
                return translation.title
    return translations[0].title if translations else f"SPU {str(spu.public_id)[:8]}"


def _spu_payload(spu: Spu, *, images=None, stores=0) -> dict:
    images = images or []
    return {
        "id": str(spu.public_id),
        "name": _title_for(spu),
        "category": _category_payload(spu.local_category),
        "cost": money_str(spu.cost_price) if spu.cost_price is not None else None,
        "price": money_str(spu.retail_price) if spu.retail_price is not None else None,
        "images": list(spu.image_urls or []) or images,
        "specs": list(spu.specs or []),
        "description": spu.description,
        "status": spu.status,
        "stores": stores,
        "activity": spu.is_activity,
        "sku_count": getattr(spu, "sku_total", None),
        "created_at": iso(spu.created_at),
    }


class AdminProductPoolView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def _queryset(self, request):
        queryset = Spu.objects.select_related("local_category").prefetch_related("translations")
        query = (request.query_params.get("q") or "").strip()
        if query:
            condition = Q(translations__title__icontains=query)
            try:
                condition |= Q(public_id=uuid.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition)
        category = (request.query_params.get("category") or "").strip()
        if category:
            queryset = (
                queryset.filter(local_category__public_id=category)
                if _is_uuid(category)
                else queryset.filter(local_category__slug=category)
            )
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status != "ALL":
            queryset = queryset.filter(status=status)
        if request.query_params.get("activity") in {"1", "true"}:
            queryset = queryset.filter(is_activity=True)
        return queryset.distinct().order_by("-created_at", "-pk")

    def get(self, request):
        rows, meta = paginate(self._queryset(request), request)
        ids = [spu.pk for spu in rows]
        images = _primary_images(ids)
        store_counts = dict(
            Offer.objects.filter(sku__spu_id__in=ids, status=Offer.Status.ACTIVE)
            .values("sku__spu_id")
            .annotate(total=Count("merchant_id", distinct=True))
            .values_list("sku__spu_id", "total")
        )
        sku_counts = dict(
            Spu.objects.filter(pk__in=ids).annotate(total=Count("skus")).values_list("pk", "total")
        )
        for spu in rows:
            spu.sku_total = sku_counts.get(spu.pk, 0)
        return Response(
            {
                "items": [
                    _spu_payload(
                        spu,
                        images=[images[spu.pk]] if spu.pk in images else [],
                        stores=store_counts.get(spu.pk, 0),
                    )
                    for spu in rows
                ],
                **meta,
            }
        )

    def post(self, request):
        payload = request.data or {}
        name = require(payload, "name", label="商品名称").strip()
        if len(name) > 80:
            raise StaffApiError(
                business_code="NAME_TOO_LONG", message="商品名称不能超过 80 个字。", status_code=400
            )
        cost = parse_amount(payload.get("cost"), field="成本价")
        price = parse_amount(payload.get("price"), field="零售价")
        if cost <= 0 or price <= 0:
            raise StaffApiError(
                business_code="PRICE_INVALID", message="成本价与零售价必须大于 0。", status_code=400
            )
        if price < cost:
            raise StaffApiError(
                business_code="PRICE_BELOW_COST",
                message="零售价不得低于成本价。",
                status_code=400,
            )
        images, specs = _validated_media_payload(payload)
        category = _resolve_category(payload.get("category"))

        spu = Spu.objects.create(
            local_category=category,
            status=payload.get("status")
            if payload.get("status") in dict(Spu.Status.choices)
            else Spu.Status.ACTIVE,
            cost_price=cost,
            retail_price=price,
            is_activity=bool(payload.get("activity")),
            description=(payload.get("description") or "").strip(),
            image_urls=images,
            specs=specs,
        )
        SpuTranslation.objects.create(
            spu=spu,
            locale="zh-CN",
            title=name,
            description=spu.description,
        )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="PRODUCT_CREATED",
            target_type="spu",
            target_id=str(spu.public_id),
            reason="",
            before_state={},
            after_state={"name": name, "cost": str(cost), "price": str(price)},
        )
        return Response({"product": _spu_payload(spu, images=images)}, status=201)


class AdminProductPoolDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def _get(self, public_id):
        spu = (
            Spu.objects.select_related("local_category")
            .prefetch_related("translations")
            .filter(public_id=public_id)
            .first()
        )
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND", message="商品不存在。", status_code=404
            )
        return spu

    def get(self, request, public_id):
        spu = self._get(public_id)
        spu.sku_total = spu.skus.count()
        images = _primary_images([spu.pk])
        stores = (
            Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE)
            .values("merchant_id")
            .distinct()
            .count()
        )
        payload = _spu_payload(
            spu, images=[images[spu.pk]] if spu.pk in images else [], stores=stores
        )
        payload["skus"] = [
            {
                "id": str(sku.public_id),
                "specification": sku.specification,
                "merchant_sku": sku.merchant_sku,
                "status": sku.status,
            }
            for sku in spu.skus.all()[:50]
        ]
        return Response({"product": payload})

    def patch(self, request, public_id):
        spu = self._get(public_id)
        payload = request.data or {}
        before = {
            "name": _title_for(spu),
            "cost": str(spu.cost_price),
            "price": str(spu.retail_price),
            "status": spu.status,
            "activity": spu.is_activity,
        }

        if "name" in payload:
            name = (payload.get("name") or "").strip()
            if not name:
                raise StaffApiError(
                    business_code="NAME_REQUIRED", message="商品名称不能为空。", status_code=400
                )
            translation = (
                spu.translations.filter(locale="zh-CN").first() or spu.translations.first()
            )
            if translation is None:
                SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=name)
            else:
                translation.title = name
                translation.save(update_fields=["title", "updated_at"])

        cost = (
            parse_amount(payload["cost"], field="成本价")
            if payload.get("cost") not in (None, "")
            else spu.cost_price
        )
        price = (
            parse_amount(payload["price"], field="零售价")
            if payload.get("price") not in (None, "")
            else spu.retail_price
        )
        if cost is not None and price is not None and price < cost:
            raise StaffApiError(
                business_code="PRICE_BELOW_COST",
                message="零售价不得低于成本价。",
                status_code=400,
            )
        if "cost" in payload:
            spu.cost_price = cost
        if "price" in payload:
            spu.retail_price = price
        if "category" in payload:
            spu.local_category = _resolve_category(payload.get("category"))
        if "description" in payload:
            spu.description = (payload.get("description") or "").strip()
        if "activity" in payload:
            spu.is_activity = bool(payload.get("activity"))
        if "status" in payload and payload.get("status") in dict(Spu.Status.choices):
            spu.status = payload["status"]
        if "images" in payload or "specs" in payload:
            images, specs = _validated_media_payload(payload)
            spu.image_urls = images
            spu.specs = specs
        spu.save()

        record_audit(
            request=request,
            actor=request.staff_account,
            action="PRODUCT_UPDATED",
            target_type="spu",
            target_id=str(spu.public_id),
            reason="",
            before_state=before,
            after_state={
                "name": _title_for(spu),
                "cost": str(spu.cost_price),
                "price": str(spu.retail_price),
                "status": spu.status,
                "activity": spu.is_activity,
            },
        )
        return Response({"product": _spu_payload(spu, images=list(spu.image_urls or []))})


class AdminProductPoolActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def post(self, request, public_id):
        spu = Spu.objects.filter(public_id=public_id).first()
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND", message="商品不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        before = {"status": spu.status}
        if action == "publish":
            spu.status = Spu.Status.ACTIVE
        elif action == "unpublish":
            spu.status = Spu.Status.INACTIVE
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        spu.save(update_fields=["status", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action="PRODUCT_STATUS_CHANGED",
            target_type="spu",
            target_id=str(spu.public_id),
            reason="",
            before_state=before,
            after_state={"status": spu.status},
        )
        return Response({"product": _spu_payload(spu, images=list(spu.image_urls or []))})


# --------------------------------------------------------------------------
# A04 商家商品管理
# --------------------------------------------------------------------------


class AdminMerchantListingsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.listings.manage"]
    view_permissions = ["catalog.listings.view"]

    def _queryset(self, request):
        queryset = Offer.objects.select_related(
            "merchant", "sku__spu__local_category", "currency"
        ).prefetch_related("sku__spu__translations")
        merchant_query = (request.query_params.get("merchant") or "").strip()
        if merchant_query:
            try:
                merchant_uuid = uuid.UUID(merchant_query)
                queryset = queryset.filter(merchant__public_id=merchant_uuid)
            except ValueError:
                queryset = queryset.filter(merchant__display_name__icontains=merchant_query)
        product_query = (request.query_params.get("product") or "").strip()
        if product_query:
            try:
                queryset = queryset.filter(sku__spu__public_id=uuid.UUID(product_query))
            except ValueError:
                raise StaffApiError(
                    business_code="PRODUCT_ID_INVALID",
                    message="商品 ID 格式不正确。",
                    status_code=400,
                ) from None
        status = (request.query_params.get("status") or "").strip().upper()
        if status == "LISTED":
            queryset = queryset.filter(status=Offer.Status.ACTIVE)
        elif status == "REMOVED":
            queryset = queryset.filter(status=Offer.Status.INACTIVE)
        return queryset.order_by("-updated_at", "-pk")

    def get(self, request):
        rows, meta = paginate(self._queryset(request), request, default_size=12)
        return Response(
            {
                "items": [
                    {
                        "id": str(offer.public_id),
                        "merchant": {
                            "id": str(offer.merchant.public_id),
                            "name": offer.merchant.display_name,
                        },
                        "product": {
                            "id": str(offer.sku.spu.public_id),
                            "name": _title_for(offer.sku.spu),
                            "category": _category_payload(offer.sku.spu.local_category),
                            "images": list(offer.sku.spu.image_urls or []),
                            "description": offer.sku.spu.description,
                            "specs": list(offer.sku.spu.specs or []),
                        },
                        "status": "LISTED" if offer.status == Offer.Status.ACTIVE else "REMOVED",
                        "cost": money_str(offer.cost_price)
                        if offer.cost_price is not None
                        else None,
                        "price": money_str(offer.current_price),
                        "currency": offer.currency.code,
                        "listed_at": iso(offer.listed_at),
                        "removed_at": iso(offer.removed_at),
                        "removed_by_platform": offer.removed_by_platform,
                    }
                    for offer in rows
                ],
                **meta,
            }
        )


class AdminMerchantListingActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.listings.manage"]
    view_permissions = ["catalog.listings.view"]

    def post(self, request, public_id):
        from django.utils import timezone

        offer = (
            Offer.objects.select_related("merchant", "sku__spu").filter(public_id=public_id).first()
        )
        if offer is None:
            raise StaffApiError(
                business_code="LISTING_NOT_FOUND", message="店铺商品关系不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        if action != "remove":
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        if offer.status != Offer.Status.ACTIVE:
            # 幂等：重复下架不重复写时间与日志。
            return Response({"listing": {"id": str(offer.public_id), "status": "REMOVED"}})

        before = {"status": "LISTED"}
        offer.status = Offer.Status.INACTIVE
        offer.removed_at = timezone.now()
        offer.removed_by_platform = True
        offer.save(update_fields=["status", "removed_at", "removed_by_platform", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action="LISTING_REMOVED",
            target_type="offer",
            target_id=str(offer.public_id),
            reason=(request.data or {}).get("reason") or "",
            before_state=before,
            after_state={"status": "REMOVED"},
            tenant_type="merchant",
            tenant_id=str(offer.merchant.public_id),
        )
        return Response({"listing": {"id": str(offer.public_id), "status": "REMOVED"}})


# --------------------------------------------------------------------------
# 共用校验
# --------------------------------------------------------------------------


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _resolve_category(value) -> LocalCategory | None:
    if not value:
        return None
    queryset = LocalCategory.objects.all()
    if _is_uuid(str(value)):
        return queryset.filter(public_id=value).first()
    return queryset.filter(slug=str(value)).first()


def _validated_media_payload(payload) -> tuple[list, list]:
    images = payload.get("images")
    if images is not None:
        if not isinstance(images, list):
            raise StaffApiError(
                business_code="IMAGES_INVALID", message="商品图片必须是数组。", status_code=400
            )
        if len(images) > MAX_IMAGES:
            raise StaffApiError(
                business_code="TOO_MANY_IMAGES",
                message=f"商品图片最多 {MAX_IMAGES} 张。",
                status_code=400,
            )
        images = [str(url).strip() for url in images if str(url).strip()]
    else:
        images = []

    specs = payload.get("specs")
    if specs is not None:
        if not isinstance(specs, list):
            raise StaffApiError(
                business_code="SPECS_INVALID", message="规格必须是数组。", status_code=400
            )
        seen = set()
        cleaned = []
        for entry in specs:
            if not isinstance(entry, dict):
                raise StaffApiError(
                    business_code="SPECS_INVALID", message="规格格式不正确。", status_code=400
                )
            name = str(entry.get("name") or "").strip()
            value = str(entry.get("value") or "").strip()
            if not name or not value:
                raise StaffApiError(
                    business_code="SPECS_INCOMPLETE",
                    message="规格名称和规格值都不能为空。",
                    status_code=400,
                )
            if len(name) > 30 or len(value) > 200:
                raise StaffApiError(
                    business_code="SPECS_TOO_LONG",
                    message="规格名称最多 30 字，规格值最多 200 字。",
                    status_code=400,
                )
            if name in seen:
                raise StaffApiError(
                    business_code="SPECS_DUPLICATED",
                    message="同一商品的规格名称不能重复。",
                    status_code=400,
                )
            seen.add(name)
            cleaned.append({"name": name, "value": value})
        specs = cleaned
    else:
        specs = []
    return images, specs


class AdminCategoriesView(OpsAPIView):
    """商品池表单与筛选用的本地类目选项（扁平列表，带中英名）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def get(self, request):
        rows = LocalCategory.objects.filter(status=LocalCategory.Status.ACTIVE).order_by(
            "path", "sort_order"
        )[:500]
        return Response(
            {
                "items": [
                    {
                        "id": str(category.public_id),
                        "name": category.name,
                        "name_zh": category.name_zh,
                        "name_en": category.name_en,
                        "path": category.path,
                        "depth": category.depth,
                    }
                    for category in rows
                ]
            }
        )


class AdminMerchantOptionsView(OpsAPIView):
    """商家商品模块的商家搜索框数据源（不依赖商家管理权限）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.listings.manage"]
    view_permissions = ["catalog.listings.view"]

    def get(self, request):
        from merchants.models import Merchant

        query = (request.query_params.get("q") or "").strip()
        queryset = Merchant.objects.exclude(onboarding_status=Merchant.OnboardingStatus.DRAFT)
        if query:
            queryset = queryset.filter(Q(display_name__icontains=query) | Q(slug__icontains=query))
        return Response(
            {
                "items": [
                    {
                        "id": str(merchant.public_id),
                        "name": merchant.display_name,
                        "status": merchant.onboarding_status,
                    }
                    for merchant in queryset.order_by("-created_at")[:20]
                ]
            }
        )
