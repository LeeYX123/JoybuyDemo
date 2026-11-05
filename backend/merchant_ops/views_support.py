"""A12 客服中心：商家会话列表、回复、标记已解决。"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, paginate, require
from merchant_ops.models import SupportConversation, SupportMessage
from merchants.models import Merchant


def _unread_count(conversation: SupportConversation) -> int:
    since = conversation.platform_last_read_at
    queryset = conversation.messages.filter(sender=SupportMessage.Sender.MERCHANT)
    if since:
        queryset = queryset.filter(created_at__gt=since)
    return queryset.count()


def _conversation_payload(conversation: SupportConversation) -> dict:
    last = conversation.messages.last()
    return {
        "id": str(conversation.public_id),
        "merchant": {
            "id": str(conversation.merchant.public_id),
            "name": conversation.merchant.display_name,
        },
        "kind": conversation.kind,
        "state": conversation.state,
        "peer_name": conversation.peer_name
        or (
            conversation.buyer.email
            if conversation.buyer_id and conversation.buyer.email
            else "商家"
        ),
        "unread": _unread_count(conversation),
        "last_message": last.text if last else "",
        "last_message_at": iso(conversation.last_message_at or conversation.created_at),
        "product": (
            {
                "id": str(conversation.spu.public_id),
                "name": _spu_title(conversation.spu),
            }
            if conversation.spu_id
            else None
        ),
    }


def _spu_title(spu) -> str:
    for translation in spu.translations.all():
        if translation.title:
            return translation.title
    return f"SPU {str(spu.public_id)[:8]}"


class AdminSupportConversationsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["support.manage"]
    view_permissions = ["support.view"]

    def get(self, request):
        queryset = SupportConversation.objects.select_related(
            "merchant", "buyer", "spu"
        ).prefetch_related("spu__translations")
        state = (request.query_params.get("state") or "").strip().upper()
        if state and state != "ALL":
            queryset = queryset.filter(state=state)
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind in {"BUYER", "PLATFORM_SUPPORT"}:
            queryset = queryset.filter(kind=kind)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(merchant__display_name__icontains=query) | Q(peer_name__icontains=query)
            )
        rows, meta = paginate(queryset, request)
        return Response({"items": [_conversation_payload(row) for row in rows], **meta})

    def post(self, request):
        """管理端主动发起一条客服会话（便于商家侧「客服中心」入口有对象）。"""

        payload = request.data or {}
        merchant = Merchant.objects.filter(
            public_id=require(payload, "merchant_id", label="店铺")
        ).first()
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        existing = SupportConversation.objects.filter(
            merchant=merchant, kind=SupportConversation.Kind.PLATFORM_SUPPORT
        ).first()
        if existing:
            return Response({"conversation": _conversation_payload(existing)})
        conversation = SupportConversation.objects.create(
            merchant=merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            state=SupportConversation.State.PENDING,
            peer_name="平台客服",
        )
        return Response({"conversation": _conversation_payload(conversation)}, status=201)


class AdminSupportConversationDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["support.manage"]
    view_permissions = ["support.view"]

    def _get(self, public_id):
        conversation = (
            SupportConversation.objects.select_related("merchant", "buyer", "order", "spu")
            .prefetch_related("spu__translations")
            .filter(public_id=public_id)
            .first()
        )
        if conversation is None:
            raise StaffApiError(
                business_code="CONVERSATION_NOT_FOUND", message="会话不存在。", status_code=404
            )
        return conversation

    def get(self, request, public_id):
        conversation = self._get(public_id)
        # 打开详情即视为平台侧已读。
        conversation.platform_last_read_at = timezone.now()
        conversation.save(update_fields=["platform_last_read_at", "updated_at"])
        payload = _conversation_payload(conversation)
        payload["messages"] = [
            {
                "id": message.pk,
                "sender": message.sender,
                "author": message.author_label,
                "text": message.text,
                "created_at": iso(message.created_at),
            }
            for message in conversation.messages.all()
        ]
        payload["order_id"] = str(conversation.order.public_id) if conversation.order_id else None
        payload["product"] = (
            {
                "id": str(conversation.spu.public_id),
                "name": _spu_title(conversation.spu),
                "image": (conversation.spu.image_urls or [None])[0],
            }
            if conversation.spu_id
            else None
        )
        return Response({"conversation": payload})

    def post(self, request, public_id):
        conversation = self._get(public_id)
        payload = request.data or {}
        action = (payload.get("action") or "reply").strip().lower()

        if action == "reply":
            text = require(payload, "text", label="回复内容").strip()
            message = SupportMessage.objects.create(
                conversation=conversation,
                sender=SupportMessage.Sender.PLATFORM,
                author_label=request.staff_account.display_name,
                text=text,
            )
            conversation.last_message_at = message.created_at
            if conversation.state == SupportConversation.State.PENDING:
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

        if action == "resolve":
            conversation.state = SupportConversation.State.RESOLVED
            conversation.save(update_fields=["state", "updated_at"])
            # 客服标记已解决只改会话状态，不替代充值/解封等资金事务。
            record_audit(
                request=request,
                actor=request.staff_account,
                action="SUPPORT_CONVERSATION_RESOLVED",
                target_type="support_conversation",
                target_id=str(conversation.public_id),
                reason="",
                before_state={},
                after_state={"state": conversation.state},
                tenant_type="merchant",
                tenant_id=str(conversation.merchant.public_id),
            )
            return Response({"conversation": _conversation_payload(conversation)})

        raise StaffApiError(
            business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
        )
