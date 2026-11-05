"""A11 平台通知推送：普通通知 + 指定店铺商品好评 + 多轮回复。"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from catalog.models import Spu
from merchant_ops.api_utils import OpsAPIView, iso, money_str, paginate, require
from merchants.models import Merchant
from notifications.models import MerchantNotification, MerchantNotificationReply
from offers.models import Offer


def _product_title(spu: Spu) -> str:
    for translation in spu.translations.all():
        if translation.title:
            return translation.title
    return f"SPU {str(spu.public_id)[:8]}"


def _notification_payload(record: MerchantNotification, *, detail: bool = False) -> dict:
    payload = {
        "id": str(record.public_id),
        "merchant": {
            "id": str(record.merchant.public_id),
            "name": record.merchant.display_name,
        },
        "kind": record.kind,
        "title": record.title,
        "content": record.content,
        "rating": record.rating,
        "images": list(record.images or []),
        "product": record.product_snapshot or None,
        "read": record.read_at is not None,
        "read_at": iso(record.read_at),
        "reply_count": record.replies.count(),
        "created_at": iso(record.created_at),
    }
    if detail:
        payload["replies"] = [
            {
                "id": reply.pk,
                "role": reply.role,
                "author": reply.author_label,
                "content": reply.content,
                "created_at": iso(reply.created_at),
            }
            for reply in record.replies.all()
        ]
    return payload


class AdminNotificationsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["notifications.manage"]
    view_permissions = ["notifications.view"]

    def get(self, request):
        queryset = MerchantNotification.objects.select_related("merchant")
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind in {"NORMAL", "REVIEW"}:
            queryset = queryset.filter(kind=kind)
        read = (request.query_params.get("read") or "").strip()
        if read in {"1", "true"}:
            queryset = queryset.filter(read_at__isnull=False)
        elif read in {"0", "false"}:
            queryset = queryset.filter(read_at__isnull=True)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(content__icontains=query)
                | Q(merchant__display_name__icontains=query)
            )
        rows, meta = paginate(queryset, request)
        return Response({"items": [_notification_payload(row) for row in rows], **meta})

    def post(self, request):
        payload = request.data or {}
        kind = (payload.get("kind") or "NORMAL").strip().upper()
        title = require(payload, "title", label="通知标题").strip()
        content = (payload.get("content") or "").strip()

        if kind == "REVIEW":
            merchant = _resolve_merchant(require(payload, "merchant_id", label="店铺"))
            spu = _resolve_listed_product(
                merchant,
                require(payload, "product_id", label="商品"),
            )
            rating = int(payload.get("rating") or 5)
            if rating < 1 or rating > 5:
                raise StaffApiError(
                    business_code="RATING_INVALID",
                    message="星级必须在 1 到 5 之间。",
                    status_code=400,
                )
            images = payload.get("images") or []
            if not isinstance(images, list) or len(images) > 5:
                raise StaffApiError(
                    business_code="IMAGES_INVALID",
                    message="评论图片最多 5 张。",
                    status_code=400,
                )
            record = MerchantNotification.objects.create(
                merchant=merchant,
                kind=MerchantNotification.Kind.REVIEW,
                title=title,
                content=content,
                spu=spu,
                product_snapshot=_product_snapshot(spu),
                rating=rating,
                images=[str(url).strip() for url in images if str(url).strip()],
                read_at=None,
                created_by=request.staff_account,
            )
            created = [record]
        else:
            # 「全部接单商家」= 所有可经营店铺，各生成一条独立站内信。
            target = (payload.get("target") or "ALL").strip().upper()
            if target == "ALL":
                merchants = list(
                    Merchant.objects.filter(
                        onboarding_status=Merchant.OnboardingStatus.ACTIVE
                    ).exclude(merchant_type=Merchant.Type.IMPORT_FALLBACK)
                )
            else:
                merchants = [_resolve_merchant(require(payload, "merchant_id", label="店铺"))]
            if not merchants:
                raise StaffApiError(
                    business_code="NO_RECIPIENT", message="没有可接收通知的商家。", status_code=400
                )
            created = [
                MerchantNotification.objects.create(
                    merchant=merchant,
                    kind=MerchantNotification.Kind.NORMAL,
                    title=title,
                    content=content,
                    created_by=request.staff_account,
                )
                for merchant in merchants
            ]

        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_NOTIFICATION_SENT",
            target_type="merchant_notification",
            target_id=str(created[0].public_id),
            reason="",
            before_state={},
            after_state={"title": title, "kind": kind, "recipients": len(created)},
        )
        return Response(
            {
                "notifications": [_notification_payload(row) for row in created],
                "count": len(created),
            },
            status=201,
        )


class AdminNotificationDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["notifications.manage"]
    view_permissions = ["notifications.view"]

    def _get(self, public_id):
        record = (
            MerchantNotification.objects.select_related("merchant")
            .prefetch_related("replies")
            .filter(public_id=public_id)
            .first()
        )
        if record is None:
            raise StaffApiError(
                business_code="NOTIFICATION_NOT_FOUND", message="通知不存在。", status_code=404
            )
        return record

    def get(self, request, public_id):
        return Response({"notification": _notification_payload(self._get(public_id), detail=True)})


class AdminNotificationReplyView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["notifications.manage"]

    def post(self, request, public_id):
        record = MerchantNotification.objects.filter(public_id=public_id).first()
        if record is None:
            raise StaffApiError(
                business_code="NOTIFICATION_NOT_FOUND", message="通知不存在。", status_code=404
            )
        content = require(request.data or {}, "content", label="回复内容").strip()
        if len(content) > 1000:
            raise StaffApiError(
                business_code="CONTENT_TOO_LONG", message="回复最多 1000 个字。", status_code=400
            )
        reply = MerchantNotificationReply.objects.create(
            notification=record,
            role=MerchantNotificationReply.Role.PLATFORM,
            author_label=request.staff_account.display_name,
            content=content,
        )
        # 平台回复后商家端重新未读（文档 M10 明确要求）。
        record.read_at = None
        record.save(update_fields=["read_at", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_NOTIFICATION_REPLIED",
            target_type="merchant_notification",
            target_id=str(record.public_id),
            reason="",
            before_state={},
            after_state={"reply_id": reply.pk},
        )
        return Response(
            {
                "reply": {
                    "id": reply.pk,
                    "role": reply.role,
                    "author": reply.author_label,
                    "content": reply.content,
                    "created_at": iso(reply.created_at),
                }
            },
            status=201,
        )


class AdminNotificationMerchantsView(OpsAPIView):
    """确认店铺选择的搜索框数据源。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["notifications.manage"]
    view_permissions = ["notifications.view"]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        queryset = Merchant.objects.exclude(merchant_type=Merchant.Type.IMPORT_FALLBACK).exclude(
            onboarding_status=Merchant.OnboardingStatus.DRAFT
        )
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


class AdminNotificationProductsView(OpsAPIView):
    """按店铺过滤「该店已上架商品」，避免管理员翻几百条下拉。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["notifications.manage"]
    view_permissions = ["notifications.view"]

    def get(self, request):
        merchant = _resolve_merchant(require(request.query_params, "merchant_id", label="店铺"))
        query = (request.query_params.get("q") or "").strip()
        spu_ids = (
            Offer.objects.filter(merchant=merchant, status=Offer.Status.ACTIVE)
            .values_list("sku__spu_id", flat=True)
            .distinct()
        )
        queryset = (
            Spu.objects.filter(pk__in=list(spu_ids))
            .select_related("local_category")
            .prefetch_related("translations")
        )
        if query:
            queryset = queryset.filter(translations__title__icontains=query).distinct()
        rows = []
        for spu in queryset[:30]:
            offer = (
                Offer.objects.select_related("currency")
                .filter(merchant=merchant, sku__spu=spu, status=Offer.Status.ACTIVE)
                .order_by("current_price")
                .first()
            )
            rows.append(
                {
                    "id": str(spu.public_id),
                    "name": _product_title(spu),
                    "category": spu.local_category.name_zh
                    if spu.local_category and spu.local_category.name_zh
                    else (spu.local_category.name if spu.local_category else ""),
                    "price": money_str(offer.current_price) if offer else None,
                    "currency": offer.currency.code if offer else "",
                    "cost": money_str(offer.cost_price) if offer and offer.cost_price else None,
                    "image": (spu.image_urls or [None])[0],
                }
            )
        return Response({"items": rows})


def _resolve_merchant(value) -> Merchant:
    merchant = Merchant.objects.filter(public_id=value).first() if value else None
    if merchant is None:
        raise StaffApiError(
            business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
        )
    return merchant


def _resolve_listed_product(merchant: Merchant, value) -> Spu:
    spu = Spu.objects.filter(public_id=value).prefetch_related("translations").first()
    if spu is None:
        raise StaffApiError(
            business_code="PRODUCT_NOT_FOUND", message="商品不存在。", status_code=404
        )
    listed = Offer.objects.filter(
        merchant=merchant, sku__spu=spu, status=Offer.Status.ACTIVE
    ).exists()
    if not listed:
        raise StaffApiError(
            business_code="PRODUCT_NOT_LISTED",
            message="该商品不属于该店铺的已上架商品。",
            status_code=400,
        )
    return spu


def _product_snapshot(spu: Spu) -> dict:
    offer = (
        Offer.objects.select_related("currency")
        .filter(sku__spu=spu, status=Offer.Status.ACTIVE)
        .order_by("current_price")
        .first()
    )
    return {
        "id": str(spu.public_id),
        "name": _product_title(spu),
        "category": spu.local_category.name if spu.local_category else "",
        "price": money_str(offer.current_price) if offer else None,
        "cost": money_str(offer.cost_price) if offer and offer.cost_price else None,
        "image": (spu.image_urls or [None])[0],
        "snapshot_at": timezone.now().isoformat(),
    }
