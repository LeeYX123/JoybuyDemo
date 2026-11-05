"""商家端 M09 消息中心 / M10 平台通知中心。

两套业务刻意分开，不共享列表：
- 会话走 ``support_conversation``（买家咨询 + 每个商家一条平台客服会话）；
- 通知走 ``notifications.MerchantNotification``（普通通知 + 商品好评推送，可多轮回复）。
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from merchant_ops.api_utils import iso, money_str, paginate
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.models import SupportConversation, SupportMessage
from merchant_ops.views_support import _spu_title
from notifications.models import MerchantNotification, MerchantNotificationReply

SUPPORT_PEER_NAME = "客服中心"


def _merchant_unread(conversation: SupportConversation) -> int:
    """商家侧未读：客服/买家发来、且晚于商家上次已读时间的消息。"""

    queryset = conversation.messages.exclude(sender=SupportMessage.Sender.MERCHANT)
    if conversation.merchant_last_read_at:
        queryset = queryset.filter(created_at__gt=conversation.merchant_last_read_at)
    return queryset.count()


def _conversation_payload(conversation: SupportConversation, *, detail=False) -> dict:
    last = conversation.messages.last()
    payload = {
        "id": str(conversation.public_id),
        "kind": conversation.kind,
        "state": conversation.state,
        "peer_name": (
            SUPPORT_PEER_NAME
            if conversation.kind == SupportConversation.Kind.PLATFORM_SUPPORT
            else (conversation.peer_name or "买家")
        ),
        "unread": _merchant_unread(conversation),
        "last_message": last.text if last else "",
        "last_message_at": iso(conversation.last_message_at or conversation.created_at),
        "product": _product_payload(conversation),
    }
    if detail:
        payload["messages"] = [
            {
                "id": message.pk,
                "sender": message.sender,
                "author": message.author_label
                or dict(SupportMessage.Sender.choices).get(message.sender, ""),
                "text": message.text,
                "created_at": iso(message.created_at),
            }
            for message in conversation.messages.all()
        ]
    return payload


def _product_payload(conversation: SupportConversation) -> dict | None:
    """买家从哪个商品发起咨询——商家必须知道，否则没法回答。"""

    if not conversation.spu_id:
        return None
    spu = conversation.spu
    # 爬虫导入的商品没有 image_urls，主图在 MediaUsage 里，必须走同一套取图逻辑。
    from merchant_ops.views_catalog import _primary_images

    image = (spu.image_urls or [""])[0] or _primary_images([spu.pk]).get(spu.pk, "")
    return {
        "id": str(spu.public_id),
        "name": _spu_title(spu),
        "category": (
            spu.local_category.name_zh or spu.local_category.name if spu.local_category_id else ""
        ),
        "price": money_str(spu.retail_price) if spu.retail_price is not None else None,
        "image": image or "",
    }


def _ensure_support_conversation(merchant) -> SupportConversation:
    conversation, _ = SupportConversation.objects.get_or_create(
        merchant=merchant,
        kind=SupportConversation.Kind.PLATFORM_SUPPORT,
        defaults={"peer_name": SUPPORT_PEER_NAME},
    )
    return conversation


class MerchantConversationsView(MerchantAPIView):
    permission_any = ("merchant.messages.use",)

    def get(self, request):
        support = _ensure_support_conversation(request.merchant)
        queryset = (
            SupportConversation.objects.select_related("spu__local_category", "buyer")
            .filter(merchant=request.merchant)
            .exclude(kind=SupportConversation.Kind.PLATFORM_SUPPORT)
            .order_by("-last_message_at", "-pk")
        )
        rows, meta = paginate(queryset, request, default_size=30)
        items = [_conversation_payload(support)]
        items.extend(_conversation_payload(row) for row in rows)
        return Response(
            {
                "items": items,
                "support_unread": _merchant_unread(support),
                "total": meta["total"] + 1,
            }
        )


class MerchantConversationDetailView(MerchantAPIView):
    permission_any = ("merchant.messages.use",)

    def get(self, request, public_id):
        conversation = _resolve_conversation(request, public_id)
        # 打开会话即标记已读，未读数归零。
        conversation.merchant_last_read_at = timezone.now()
        conversation.save(update_fields=["merchant_last_read_at", "updated_at"])
        return Response({"conversation": _conversation_payload(conversation, detail=True)})


class MerchantConversationReplyView(MerchantAPIView):
    permission_any = ("merchant.messages.use",)

    def post(self, request, public_id):
        conversation = _resolve_conversation(request, public_id)
        text = str((request.data or {}).get("text") or "").strip()
        if not text:
            raise StaffApiError(
                business_code="MESSAGE_EMPTY", message="消息内容不能为空。", status_code=400
            )
        if len(text) > 2000:
            raise StaffApiError(
                business_code="MESSAGE_TOO_LONG", message="消息不能超过 2000 字。", status_code=400
            )
        message = SupportMessage.objects.create(
            conversation=conversation,
            sender=SupportMessage.Sender.MERCHANT,
            author_label=request.merchant.display_name,
            text=text,
        )
        conversation.last_message_at = message.created_at
        if conversation.kind == SupportConversation.Kind.PLATFORM_SUPPORT:
            conversation.state = SupportConversation.State.PROCESSING
        conversation.save(update_fields=["last_message_at", "state", "updated_at"])
        return Response(
            {
                "message": {
                    "id": message.pk,
                    "sender": message.sender,
                    "author": message.author_label,
                    "text": message.text,
                    "created_at": iso(message.created_at),
                }
            },
            status=201,
        )


def _resolve_conversation(request, public_id) -> SupportConversation:
    conversation = (
        SupportConversation.objects.select_related("spu__local_category", "buyer")
        .filter(merchant=request.merchant, public_id=public_id)
        .first()
    )
    if conversation is None:
        raise StaffApiError(
            business_code="CONVERSATION_NOT_FOUND",
            message="会话不存在或不属于当前店铺。",
            status_code=404,
        )
    return conversation


# --------------------------------------------------------------------------
# M10 平台通知中心
# --------------------------------------------------------------------------


def _notification_payload(record: MerchantNotification, *, detail=False) -> dict:
    payload = {
        "id": str(record.public_id),
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
        # 好评详情按「星级 → 评论文字 → 图片 → 时间」展示，图片不能排到时间后面。
        payload["layout"] = "review" if record.kind == MerchantNotification.Kind.REVIEW else "plain"
    return payload


def _notification_queryset(request):
    queryset = MerchantNotification.objects.filter(merchant=request.merchant)
    state = (request.query_params.get("state") or "ALL").strip().upper()
    if state == "UNREAD":
        queryset = queryset.filter(read_at__isnull=True)
    elif state == "READ":
        queryset = queryset.filter(read_at__isnull=False)
    query = (request.query_params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(content__icontains=query))
    return queryset.order_by("-created_at", "-pk")


class MerchantNotificationsView(MerchantAPIView):
    permission_any = ("merchant.notifications.view",)

    def get(self, request):
        rows, meta = paginate(_notification_queryset(request), request)
        base = MerchantNotification.objects.filter(merchant=request.merchant)
        counts = {
            "ALL": base.count(),
            "UNREAD": base.filter(read_at__isnull=True).count(),
            "READ": base.filter(read_at__isnull=False).count(),
        }
        return Response(
            {"items": [_notification_payload(record) for record in rows], "counts": counts, **meta}
        )


class MerchantNotificationDetailView(MerchantAPIView):
    permission_any = ("merchant.notifications.view",)

    def get(self, request, public_id):
        record = _resolve_notification(request, public_id)
        if record.read_at is None:
            record.read_at = timezone.now()
            record.save(update_fields=["read_at", "updated_at"])
        return Response({"notification": _notification_payload(record, detail=True)})


class MerchantNotificationReplyView(MerchantAPIView):
    permission_any = ("merchant.notifications.view",)

    def post(self, request, public_id):
        record = _resolve_notification(request, public_id)
        content = str((request.data or {}).get("content") or "").strip()
        if not content:
            raise StaffApiError(
                business_code="REPLY_EMPTY", message="回复内容不能为空。", status_code=400
            )
        if len(content) > 1000:
            raise StaffApiError(
                business_code="REPLY_TOO_LONG", message="回复不能超过 1000 字。", status_code=400
            )
        reply = MerchantNotificationReply.objects.create(
            notification=record,
            role=MerchantNotificationReply.Role.MERCHANT,
            author_label=request.merchant.display_name,
            content=content,
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


class MerchantNotificationsMarkAllReadView(MerchantAPIView):
    permission_any = ("merchant.notifications.view",)

    def post(self, request):
        updated = MerchantNotification.objects.filter(
            merchant=request.merchant, read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response({"updated": updated})


def _resolve_notification(request, public_id) -> MerchantNotification:
    record = MerchantNotification.objects.filter(
        merchant=request.merchant, public_id=public_id
    ).first()
    if record is None:
        raise StaffApiError(
            business_code="NOTIFICATION_NOT_FOUND",
            message="通知不存在或不属于当前店铺。",
            status_code=404,
        )
    return record
