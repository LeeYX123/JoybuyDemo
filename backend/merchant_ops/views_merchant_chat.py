"""用户 ↔ 商家一对一会话（需求 19 / 批次 V2）。

两条接口线，鉴权与既有接口保持一致：

- 买家侧 ``/api/v1/account/merchant-chat/*``：买家会话 + **白名单门禁**
  （``BuyerAccount.purchase_whitelisted``，非白名单 403 ``NOT_WHITELISTED``）；
- 商家侧 ``/api/v1/merchant/chats*``：员工会话 + 店铺上下文 +
  ``merchant.messages.use`` 权限，跨店一律 404。

与 ``SupportConversation``（商家 ↔ 平台客服）完全独立，互不影响；Crisp 镜像走
``bm:{buyer_public_id}:{merchant_public_id}`` 线程（需求 19.2）。
"""

from datetime import UTC, datetime

from django.db.models import F
from django.utils import timezone
from rest_framework.response import Response

from accounts_buyers.api_exceptions import BuyerApiError
from accounts_buyers.models import BuyerAccount
from accounts_buyers.views import BuyerCsrfAPIView
from accounts_staff.api_exceptions import StaffApiError
from merchant_ops.api_utils import iso
from merchant_ops.crisp_mirror import merchant_chat_buyer_name, queue_merchant_chat_mirror
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.models import MerchantChatMessage, MerchantChatThread
from merchants.models import Merchant

MAX_MESSAGE_LENGTH = 2000


# --------------------------------------------------------------------------
# 公共工具
# --------------------------------------------------------------------------


def _require_chat_buyer(request) -> BuyerAccount:
    """买家会话 + 白名单门禁：未登录 401，非白名单 403。"""

    buyer = getattr(request, "buyer_account", None)
    if buyer is None:
        raise BuyerApiError(
            business_code="BUYER_AUTH_REQUIRED",
            message="请先登录后再操作。",
            status_code=401,
        )
    if not buyer.purchase_whitelisted:
        raise BuyerApiError(
            business_code="NOT_WHITELISTED",
            message="当前账号暂未开通与商家沟通的权限。",
            status_code=403,
        )
    return buyer


def _validated_body(payload, error_cls) -> str:
    body = str((payload or {}).get("body") or "").strip()
    if not body:
        raise error_cls(
            business_code="MESSAGE_EMPTY", message="消息内容不能为空。", status_code=400
        )
    if len(body) > MAX_MESSAGE_LENGTH:
        raise error_cls(
            business_code="MESSAGE_TOO_LONG",
            message=f"消息不能超过 {MAX_MESSAGE_LENGTH} 字。",
            status_code=400,
        )
    return body


def _parse_after(raw, error_cls) -> datetime | None:
    """``?after=<iso>``：只取严格晚于该时间的消息。空值返回 None。"""

    text = str(raw or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise error_cls(
            business_code="AFTER_INVALID",
            message="after 必须是 ISO 8601 时间。",
            status_code=400,
        ) from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def _message_payload(message: MerchantChatMessage) -> dict:
    return {
        "id": message.pk,
        "sender_kind": message.sender_kind,
        "body": message.body,
        "created_at": iso(message.created_at),
        "read_at": iso(message.read_at),
    }


def _buyer_thread_payload(thread: MerchantChatThread) -> dict:
    merchant = thread.merchant
    return {
        "id": str(thread.public_id),
        "merchant": {
            "public_id": merchant.public_id,
            "display_name": merchant.display_name,
            "avatar_url": merchant.avatar_url or "",
        },
        "status": thread.status,
        "last_message_at": iso(thread.last_message_at),
        "unread": thread.buyer_unread,
        "created_at": iso(thread.created_at),
    }


def _merchant_thread_payload(thread: MerchantChatThread) -> dict:
    last = thread.messages.last()
    buyer = thread.buyer
    return {
        "id": str(thread.public_id),
        "buyer": {
            "id": str(buyer.public_id),
            "display_name": merchant_chat_buyer_name(buyer),
            # 头像占位（买家账号暂无头像字段，批次 V3 前端用默认图）。
            "avatar_url": "",
        },
        "status": thread.status,
        "unread": thread.merchant_unread,
        "last_message": last.body if last else "",
        "last_message_kind": last.sender_kind if last else "",
        "last_message_at": iso(thread.last_message_at or thread.created_at),
        "created_at": iso(thread.created_at),
    }


def _buyer_thread(request, public_id) -> MerchantChatThread:
    thread = (
        MerchantChatThread.objects.select_related("merchant")
        .filter(buyer=request.buyer_account, public_id=public_id)
        .first()
    )
    if thread is None:
        raise BuyerApiError(
            business_code="THREAD_NOT_FOUND",
            message="会话不存在。",
            status_code=404,
        )
    return thread


def _merchant_thread(request, public_id) -> MerchantChatThread:
    thread = (
        MerchantChatThread.objects.select_related("buyer")
        .filter(merchant=request.merchant, public_id=public_id)
        .first()
    )
    if thread is None:
        raise StaffApiError(
            business_code="THREAD_NOT_FOUND",
            message="会话不存在或不属于当前店铺。",
            status_code=404,
        )
    return thread


def _mark_read(thread: MerchantChatThread, *, side: str) -> None:
    """打开会话即已读：把对方消息标 read_at 并清零本方未读。"""

    other_kind = (
        MerchantChatMessage.SenderKind.MERCHANT
        if side == "buyer"
        else MerchantChatMessage.SenderKind.BUYER
    )
    thread.messages.filter(sender_kind=other_kind, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    if side == "buyer":
        thread.buyer_unread = 0
        thread.save(update_fields=["buyer_unread", "updated_at"])
    else:
        thread.merchant_unread = 0
        thread.save(update_fields=["merchant_unread", "updated_at"])


def _touch_after_send(thread: MerchantChatThread, message: MerchantChatMessage, *, side: str):
    """落库后更新最后消息时间 + 对方未读；返回刷新后的 thread。"""

    updates = {
        "last_message_at": message.created_at,
        "updated_at": timezone.now(),
    }
    queryset = MerchantChatThread.objects.filter(pk=thread.pk)
    if side == "buyer":
        queryset.update(merchant_unread=F("merchant_unread") + 1, **updates)
    else:
        queryset.update(buyer_unread=F("buyer_unread") + 1, **updates)
    thread.refresh_from_db()
    return thread


# --------------------------------------------------------------------------
# 买家侧 API
# --------------------------------------------------------------------------


class BuyerMerchantChatThreadsView(BuyerCsrfAPIView):
    """GET 我的全部会话 / POST 按商家 slug get-or-create 会话。"""

    def get(self, request):
        buyer = _require_chat_buyer(request)
        threads = MerchantChatThread.objects.select_related("merchant").filter(buyer=buyer)
        items = [_buyer_thread_payload(thread) for thread in threads]
        return Response({"items": items, "total": len(items)})

    def post(self, request):
        buyer = _require_chat_buyer(request)
        slug = str((request.data or {}).get("merchant") or "").strip()
        if not slug:
            raise BuyerApiError(
                business_code="MERCHANT_REQUIRED",
                message="请指定商家。",
                status_code=400,
            )
        merchant = Merchant.objects.filter(slug=slug).first()
        if merchant is None:
            raise BuyerApiError(
                business_code="MERCHANT_NOT_FOUND",
                message="商家不存在。",
                status_code=404,
            )
        thread, created = MerchantChatThread.objects.get_or_create(buyer=buyer, merchant=merchant)
        return Response(
            {"thread": _buyer_thread_payload(thread)},
            status=201 if created else 200,
        )


class BuyerMerchantChatMessagesView(BuyerCsrfAPIView):
    """GET 会话消息（支持 ``after`` 增量，读后清零未读）/ POST 发消息。"""

    def get(self, request, public_id):
        _require_chat_buyer(request)
        thread = _buyer_thread(request, public_id)
        after = _parse_after(request.query_params.get("after"), BuyerApiError)
        queryset = thread.messages.all()
        if after is not None:
            queryset = queryset.filter(created_at__gt=after)
        messages = list(queryset)
        _mark_read(thread, side="buyer")
        return Response(
            {
                "thread": _buyer_thread_payload(thread),
                "messages": [_message_payload(message) for message in messages],
            }
        )

    def post(self, request, public_id):
        _require_chat_buyer(request)
        thread = _buyer_thread(request, public_id)
        body = _validated_body(request.data, BuyerApiError)
        message = MerchantChatMessage.objects.create(
            thread=thread,
            sender_kind=MerchantChatMessage.SenderKind.BUYER,
            body=body,
        )
        _touch_after_send(thread, message, side="buyer")
        # 批次 V2：落库后镜像到 Crisp（事务提交后才发，失败不影响本接口）。
        queue_merchant_chat_mirror(message)
        return Response(
            {
                "message": _message_payload(message),
                "thread": _buyer_thread_payload(thread),
            },
            status=201,
        )


# --------------------------------------------------------------------------
# 商家侧 API
# --------------------------------------------------------------------------


class MerchantChatThreadsView(MerchantAPIView):
    permission_any = ("merchant.messages.use",)

    def get(self, request):
        threads = MerchantChatThread.objects.select_related("buyer").filter(
            merchant=request.merchant
        )
        items = [_merchant_thread_payload(thread) for thread in threads]
        return Response({"items": items, "total": len(items)})


class MerchantChatMessagesView(MerchantAPIView):
    permission_any = ("merchant.messages.use",)

    def get(self, request, public_id):
        thread = _merchant_thread(request, public_id)
        messages = list(thread.messages.all())
        _mark_read(thread, side="merchant")
        return Response(
            {
                "thread": _merchant_thread_payload(thread),
                "messages": [_message_payload(message) for message in messages],
            }
        )

    def post(self, request, public_id):
        thread = _merchant_thread(request, public_id)
        body = _validated_body(request.data, StaffApiError)
        message = MerchantChatMessage.objects.create(
            thread=thread,
            sender_kind=MerchantChatMessage.SenderKind.MERCHANT,
            body=body,
        )
        _touch_after_send(thread, message, side="merchant")
        queue_merchant_chat_mirror(message)
        return Response(
            {
                "message": _message_payload(message),
                "thread": _merchant_thread_payload(thread),
            },
            status=201,
        )
