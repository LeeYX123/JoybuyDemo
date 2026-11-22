"""买家 ↔ 平台客服统一会话（需求 21 / 批次 X）。

全站右下角【客服】入口的后端：

- 买家侧 ``/api/v1/account/support-chat/*``：**所有登录买家**可用（**不要求白名单**），
  一个买家永远只有一条线程；未登录 401 ``BUYER_AUTH_REQUIRED``；
- 管理端 ``/api/v1/admin/support-chat/*``：放在 ``views_support.py``，沿用既有
  ``support.view`` / ``support.manage`` 权限；本文件只提供共用 payload/校验工具；
- Crisp 镜像 thread_key ``bp:{buyer_public_id}``，与 V2 的 ``bm:``（买家↔商家）、
  商家 ↔ 平台的 ``merchant:`` 完全隔离。

复用 ``views_merchant_chat`` 的 ``after`` 解析与正文校验，避免两套口径漂移。
"""

from django.db.models import F
from django.utils import timezone
from rest_framework.response import Response

from accounts_buyers.api_exceptions import BuyerApiError
from accounts_buyers.views import BuyerCsrfAPIView
from merchant_ops.api_utils import iso
from merchant_ops.crisp_mirror import merchant_chat_buyer_name, queue_support_chat_mirror
from merchant_ops.models import SupportChatMessage, SupportChatThread
from merchant_ops.views_merchant_chat import _parse_after, _validated_body


def require_support_buyer(request):
    """只用买家会话，不做白名单门禁：所有登录买家都能联系平台客服。"""

    buyer = getattr(request, "buyer_account", None)
    if buyer is None:
        raise BuyerApiError(
            business_code="BUYER_AUTH_REQUIRED",
            message="请先登录后再操作。",
            status_code=401,
        )
    return buyer


def message_payload(message: SupportChatMessage) -> dict:
    return {
        "id": message.pk,
        "sender_kind": message.sender_kind,
        "body": message.body,
        "created_at": iso(message.created_at),
        "read_at": iso(message.read_at),
    }


def buyer_thread_payload(thread: SupportChatThread) -> dict:
    return {
        "id": str(thread.public_id),
        "status": thread.status,
        "last_message_at": iso(thread.last_message_at),
        "buyer_unread": thread.buyer_unread,
        "created_at": iso(thread.created_at),
    }


def _last_message_info(thread: SupportChatThread) -> tuple[str, str]:
    """最后一条消息的 (正文, sender_kind)；管理端列表用 annotate 预取，避免 N+1。"""

    if hasattr(thread, "last_message_body"):
        return thread.last_message_body or "", thread.last_message_kind or ""
    last = thread.messages.last()
    return (last.body, last.sender_kind) if last else ("", "")


def admin_thread_payload(thread: SupportChatThread) -> dict:
    body, kind = _last_message_info(thread)
    buyer = thread.buyer
    return {
        "id": str(thread.public_id),
        "buyer": {
            "id": str(buyer.public_id),
            "display_name": merchant_chat_buyer_name(buyer),
            # 买家账号暂无头像字段（与批次 V3 口径一致，前端用默认图）。
            "avatar_url": "",
            "email": (buyer.email or "").strip(),
        },
        "status": thread.status,
        "unread": thread.support_unread,
        "last_message": body,
        "last_message_kind": kind,
        "last_message_at": iso(thread.last_message_at or thread.created_at),
        "created_at": iso(thread.created_at),
    }


def mark_read(thread: SupportChatThread, *, side: str) -> None:
    """打开会话即已读：把对方消息标 read_at 并清零本方未读。"""

    other_kind = (
        SupportChatMessage.SenderKind.SUPPORT
        if side == "buyer"
        else SupportChatMessage.SenderKind.BUYER
    )
    thread.messages.filter(sender_kind=other_kind, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    if side == "buyer":
        SupportChatThread.objects.filter(pk=thread.pk).update(
            buyer_unread=0, updated_at=timezone.now()
        )
        thread.buyer_unread = 0
    else:
        SupportChatThread.objects.filter(pk=thread.pk).update(
            support_unread=0, updated_at=timezone.now()
        )
        thread.support_unread = 0


def touch_after_send(
    thread: SupportChatThread, message: SupportChatMessage, *, side: str
) -> SupportChatThread:
    """落库后更新最后消息时间 + 对方未读；返回刷新后的 thread。"""

    updates = {
        "last_message_at": message.created_at,
        "updated_at": timezone.now(),
    }
    queryset = SupportChatThread.objects.filter(pk=thread.pk)
    if side == "buyer":
        queryset.update(support_unread=F("support_unread") + 1, **updates)
    else:
        queryset.update(buyer_unread=F("buyer_unread") + 1, **updates)
    thread.refresh_from_db()
    return thread


def buyer_thread(request) -> SupportChatThread:
    thread = SupportChatThread.objects.filter(buyer=request.buyer_account).first()
    if thread is None:
        raise BuyerApiError(
            business_code="THREAD_NOT_FOUND",
            message="会话不存在，请先联系客服。",
            status_code=404,
        )
    return thread


# --------------------------------------------------------------------------
# 买家侧 API（免白名单）
# --------------------------------------------------------------------------


class BuyerSupportChatThreadView(BuyerCsrfAPIView):
    """POST 取（或首次创建）我的平台客服会话。"""

    def post(self, request):
        buyer = require_support_buyer(request)
        thread, created = SupportChatThread.objects.get_or_create(buyer=buyer)
        return Response(
            {"thread": buyer_thread_payload(thread)},
            status=201 if created else 200,
        )


class BuyerSupportChatMessagesView(BuyerCsrfAPIView):
    """GET 消息（``after`` 增量，读后清零未读）/ POST 发消息。"""

    def get(self, request):
        require_support_buyer(request)
        thread = buyer_thread(request)
        after = _parse_after(request.query_params.get("after"), BuyerApiError)
        queryset = thread.messages.all()
        if after is not None:
            queryset = queryset.filter(created_at__gt=after)
        messages = list(queryset)
        mark_read(thread, side="buyer")
        return Response(
            {
                "thread": buyer_thread_payload(thread),
                "messages": [message_payload(message) for message in messages],
            }
        )

    def post(self, request):
        require_support_buyer(request)
        thread = buyer_thread(request)
        body = _validated_body(request.data, BuyerApiError)
        message = SupportChatMessage.objects.create(
            thread=thread,
            sender_kind=SupportChatMessage.SenderKind.BUYER,
            body=body,
        )
        touch_after_send(thread, message, side="buyer")
        # 落库后镜像到 Crisp（事务提交后才发，失败不影响本接口）。
        queue_support_chat_mirror(message)
        return Response(
            {
                "message": message_payload(message),
                "thread": buyer_thread_payload(thread),
            },
            status=201,
        )
