"""Crisp 入站同步（批次 AA / 需求 23.2 / 决策 Q3、Q7(a)）。

数据库是唯一事实源，Crisp 只是副本：客服在 Crisp Inbox 里的人工回复由本模块
按线程拉回来落库，买家端 / 商家端既有的 5s 轮询立刻就能看到。实测事实见
``var/cs_sync_panel_20261123/findings.md``（A1/A2/A5/A6、B6）。

设计口径：

- **不做 cron**（Q7(a)）：只有正在被查看的线程才拉取，由买家/商家轮询触发的
  ``GET .../messages`` 顺带调用 ``pull_thread``；
- **线程节流**：同一线程 ``INBOUND_THROTTLE_SECONDS``（**5s**，与前端 5s 轮询对齐，
  验收要求端到端 ≤10s）内最多一次 HTTP，另加 ``INBOUND_MAX_PER_MINUTE``（**12 次**）
  的每线程每分钟上限兜底 → 单线程 ≤12 请求/分钟；
- **增量游标**：``<thread>.inbound_cursor_ms`` 直接作为 ``timestamp_after``（毫秒）；
  首次（游标为空）只拉最近 ``FIRST_PULL_WINDOW_HOURS`` 小时，避免全量回填；
- **只认真实人工回复**：``from=operator`` 且 ``user.user_id`` 存在（且不等于
  ``session_id``）。我们镜像过去的 operator 消息是 ``user={type:"website"}``、
  没有 ``user_id``，必须跳过，否则会把自己发的消息再灌回库里（回声）；
- **限时**：同步调用有墙钟预算 ``CALL_BUDGET_SECONDS``（2s，且作为单次 HTTP 超时），
  超时/失败只记 ``CrispMirrorLog``（status=failed），绝不影响用户请求；
- **去重**：Crisp ``fingerprint``（number）落到消息表 ``crisp_fingerprint``，
  ``(thread, crisp_fingerprint)`` 唯一，重复拉取不产生重复消息。

范围：``bp:``（买家 ↔ 平台）、``merchant:``（商家 ↔ 平台）、``bm:``（买家 ↔ 商家）
三条线程都回填。``bm:`` 的人工回复落成 ``MerchantChatMessage(sender_kind=support)``，
买家面板与商家端消息中心都显示成"客服回复"（区别于商家本人）。
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from merchant_ops import crisp_mirror
from merchant_ops.models import (
    CrispMirrorLog,
    CrispMirrorSession,
    MerchantChatMessage,
    MerchantChatThread,
    SupportChatMessage,
    SupportChatThread,
    SupportConversation,
    SupportMessage,
)

logger = logging.getLogger(__name__)

# 同一线程两次拉取的最小间隔（秒）。**5s**：前端面板本身就是 5s 轮询，节流再放 20s
# 会让"Crisp 人工回复 → 面板可见"最坏叠到 25s（验收实测 18.3s 不过）；改成 5s 后
# 最坏 ≈5s+5s=10s 以内。每次拉取仍只发 1 个 HTTP。
INBOUND_THROTTLE_SECONDS = 5
# 每线程每分钟最多多少次拉取（在 5s 节流之上的兜底，防多标签页/脚本滥用）。
# 5s 节流本身就是 12 次/分钟，所以正常轮询不会撞到上限。
INBOUND_MAX_PER_MINUTE = 12
# 单次请求线程内允许占用的墙钟时间：同时也是单次 HTTP 超时。
CALL_BUDGET_SECONDS = 2.0
# 首次拉取（没有游标）只回看最近多少小时，避免把历史会话全量灌进库。
FIRST_PULL_WINDOW_HOURS = 72
# 与消息表 ``body`` 上限一致（Crisp 正文可能更长，落库前截断）。
MAX_BODY_LENGTH = 2000
# 入站失败在 CrispMirrorLog 里共用一个 message_id（每线程一行，可反复覆盖）。
INBOUND_LOG_MESSAGE_ID = "inbound_pull"

STATUS_PULLED = "pulled"
STATUS_THROTTLED = "throttled"
STATUS_SKIPPED = "skipped"
STATUS_UNSUPPORTED = "unsupported"
STATUS_FAILED = "failed"


@dataclass
class ThreadTarget:
    """入站同步的落库目标：``bp`` → SupportChatThread，``merchant`` → SupportConversation。"""

    kind: str
    obj: object


# --------------------------------------------------------------------------
# 线程解析
# --------------------------------------------------------------------------


def _resolve_target(thread_key: str) -> ThreadTarget | None:
    prefix, _, rest = str(thread_key or "").partition(":")
    rest = rest.strip()
    if not rest:
        return None
    if prefix == "bp":
        try:
            thread = SupportChatThread.objects.filter(buyer__public_id=rest).first()
        except (ValidationError, ValueError):
            return None
        return ThreadTarget("bp", thread) if thread is not None else None
    if prefix == "merchant":
        try:
            conversation = (
                SupportConversation.objects.filter(
                    merchant__public_id=rest,
                    kind=SupportConversation.Kind.PLATFORM_SUPPORT,
                )
                .order_by("-last_message_at", "-pk")
                .first()
            )
        except (ValidationError, ValueError):
            return None
        return ThreadTarget("merchant", conversation) if conversation is not None else None
    if prefix == "bm":
        buyer_id, _, merchant_id = rest.partition(":")
        if not merchant_id.strip():
            return None
        try:
            thread = MerchantChatThread.objects.filter(
                buyer__public_id=buyer_id.strip(),
                merchant__public_id=merchant_id.strip(),
            ).first()
        except (ValidationError, ValueError):
            return None
        return ThreadTarget("bm", thread) if thread is not None else None
    return None


def _messages_path(session_id: str, after_ms: int) -> str:
    website_id = crisp_mirror.crisp_config()["website_id"]
    return (
        f"/website/{website_id}/conversation/{session_id}/messages?timestamp_after={int(after_ms)}"
    )


def _get_messages(session_id: str, after_ms: int, timeout: float) -> dict:
    """拉一个会话里 ``timestamp_after`` 之后的消息（单独成函数便于测试 mock）。"""

    return crisp_mirror._http_request(
        "GET", _messages_path(session_id, after_ms), None, timeout=timeout
    )


# --------------------------------------------------------------------------
# 消息识别
# --------------------------------------------------------------------------


def is_operator_reply(item) -> bool:
    """是否"Crisp Inbox 里真实人工客服"的回复（见 findings A5）。

    - ``from`` 必须是 ``operator``；
    - ``user.user_id`` 必须存在 —— 这是**唯一可靠**判据：我们镜像过去的 operator
      消息 ``user={type:"website",nickname:店名}`` 没有 ``user_id``；
    - ``user_id`` 等于 ``session_id`` 的不要（那是访客自身）。

    注意（**2026-11-23 实测修正**）：``user.type == "website"`` **不能**当作排除条件 ——
    用 website API 以 operator 身份发消息时，Crisp 会把 ``user.type`` 补成
    ``website``（真实 Inbox 回复没有该字段），所以"有 type 就跳过"会误杀用 API
    模拟的人工回复。真正区分镜像与人工的只有 ``user_id`` 的有无。
    """

    if not isinstance(item, dict):
        return False
    if str(item.get("from") or "").strip() != "operator":
        return False
    if str(item.get("type") or "text").strip() != "text":
        return False
    user = item.get("user")
    if not isinstance(user, dict):
        return False
    user_id = str(user.get("user_id") or "").strip()
    if not user_id:
        # 我方镜像：只有 type + nickname，没有 user_id。
        return False
    session_id = str(item.get("session_id") or "").strip()
    return not (session_id and user_id == session_id)


def _fingerprint(item: dict, session_id: str, body: str) -> int:
    """取 Crisp ``fingerprint``（number）；缺失时用 SHA-256 前 48 bit 兜底。"""

    value = item.get("fingerprint")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    stamp = str(item.get("timestamp") or "").strip()
    digest = hashlib.sha256(f"{session_id}:{stamp}:{body}".encode()).hexdigest()
    return int(digest[:12], 16)


def _message_body(item: dict) -> str:
    content = item.get("content")
    if content is None:
        return ""
    return str(content).strip()[:MAX_BODY_LENGTH]


def _operator_label(item: dict) -> str:
    user = item.get("user") or {}
    nickname = str(user.get("nickname") or "").strip() if isinstance(user, dict) else ""
    return nickname or crisp_mirror.platform_nickname()


# --------------------------------------------------------------------------
# 落库
# --------------------------------------------------------------------------


def _store_support_chat_reply(thread: SupportChatThread, body: str, fingerprint: int) -> bool:
    try:
        with transaction.atomic():
            message = SupportChatMessage.objects.create(
                thread=thread,
                sender_kind=SupportChatMessage.SenderKind.SUPPORT,
                body=body,
                source="crisp",
                crisp_fingerprint=fingerprint,
            )
    except IntegrityError:
        # 另一个请求刚并发写入同一条（fingerprint 唯一）→ 视为已同步。
        return False
    SupportChatThread.objects.filter(pk=thread.pk).update(
        buyer_unread=F("buyer_unread") + 1,
        last_message_at=message.created_at,
        updated_at=timezone.now(),
    )
    logger.info(
        "crisp inbound message stored",
        extra={"event": "crisp_inbound_stored", "kind": "bp", "message_id": message.pk},
    )
    return True


def _store_platform_reply(
    conversation: SupportConversation, body: str, fingerprint: int, author: str
) -> bool:
    try:
        with transaction.atomic():
            message = SupportMessage.objects.create(
                conversation=conversation,
                sender=SupportMessage.Sender.PLATFORM,
                author_label=author,
                text=body,
                source="crisp",
                crisp_fingerprint=fingerprint,
            )
    except IntegrityError:
        return False
    SupportConversation.objects.filter(pk=conversation.pk).update(
        last_message_at=message.created_at,
        updated_at=timezone.now(),
    )
    logger.info(
        "crisp inbound message stored",
        extra={"event": "crisp_inbound_stored", "kind": "merchant", "message_id": message.pk},
    )
    return True


def _store_merchant_chat_reply(thread: MerchantChatThread, body: str, fingerprint: int) -> bool:
    """``bm:`` 线程的客服回复：落成 ``sender_kind=support``，买家/商家两端都可见。"""

    try:
        with transaction.atomic():
            message = MerchantChatMessage.objects.create(
                thread=thread,
                sender_kind=MerchantChatMessage.SenderKind.SUPPORT,
                body=body,
                source="crisp",
                crisp_fingerprint=fingerprint,
            )
    except IntegrityError:
        return False
    # 买家是主要接收方：未读 +1；商家端打开会话即可看到（列表预览同步更新）。
    MerchantChatThread.objects.filter(pk=thread.pk).update(
        buyer_unread=F("buyer_unread") + 1,
        last_message_at=message.created_at,
        updated_at=timezone.now(),
    )
    logger.info(
        "crisp inbound message stored",
        extra={"event": "crisp_inbound_stored", "kind": "bm", "message_id": message.pk},
    )
    return True


def _import_messages(target: ThreadTarget, items: list, session_id: str) -> int:
    imported = 0
    for item in items:
        if not is_operator_reply(item):
            continue
        body = _message_body(item)
        if not body:
            continue
        fingerprint = _fingerprint(item, session_id, body)
        if target.kind == "bp":
            created = _store_support_chat_reply(target.obj, body, fingerprint)
        elif target.kind == "bm":
            created = _store_merchant_chat_reply(target.obj, body, fingerprint)
        else:
            created = _store_platform_reply(target.obj, body, fingerprint, _operator_label(item))
        if created:
            imported += 1
    return imported


def _max_timestamp_ms(items: list, fallback: int) -> int:
    stamps = []
    for item in items:
        value = item.get("timestamp") if isinstance(item, dict) else None
        if isinstance(value, int) and not isinstance(value, bool):
            stamps.append(value)
        elif isinstance(value, float) and value.is_integer():
            stamps.append(int(value))
    return max(stamps) if stamps else fallback


# --------------------------------------------------------------------------
# 节流 / 游标 / 失败日志
# --------------------------------------------------------------------------


REASON_WINDOW = "window"
REASON_MINUTE_CAP = "minute_cap"


def _claim_throttle_slot(target: ThreadTarget, now: datetime) -> tuple[bool, str]:
    """原子占用本线程的拉取名额；抢不到返回 ``(False, 原因)``（不消耗配额）。

    两道闸：5s 窗口（``last_inbound_at``）+ 每线程每分钟 ``INBOUND_MAX_PER_MINUTE``
    次（``inbound_window_start`` / ``inbound_window_count``）。都用条件 UPDATE 抢占，
    多标签页/并发轮询不会双发。
    """

    model = target.obj.__class__
    threshold = now - timedelta(seconds=INBOUND_THROTTLE_SECONDS)
    claimed = (
        model.objects.filter(pk=target.obj.pk)
        .filter(Q(last_inbound_at__isnull=True) | Q(last_inbound_at__lte=threshold))
        .update(last_inbound_at=now)
    )
    if not claimed:
        return False, REASON_WINDOW
    target.obj.last_inbound_at = now

    minute_start = now.replace(second=0, microsecond=0)
    # 新的一分钟（或第一次）→ 计数重置为 1。
    reset = (
        model.objects.filter(pk=target.obj.pk)
        .filter(Q(inbound_window_start__isnull=True) | Q(inbound_window_start__lt=minute_start))
        .update(inbound_window_start=minute_start, inbound_window_count=1)
    )
    if reset:
        target.obj.inbound_window_start = minute_start
        target.obj.inbound_window_count = 1
        return True, ""
    bumped = model.objects.filter(
        pk=target.obj.pk,
        inbound_window_start=minute_start,
        inbound_window_count__lt=INBOUND_MAX_PER_MINUTE,
    ).update(inbound_window_count=F("inbound_window_count") + 1)
    if bumped:
        return True, ""
    return False, REASON_MINUTE_CAP


def _advance_cursor(target: ThreadTarget, cursor_ms: int) -> None:
    target.obj.__class__.objects.filter(pk=target.obj.pk).update(inbound_cursor_ms=cursor_ms)
    target.obj.inbound_cursor_ms = cursor_ms


def _log_failure(thread_key: str, error: str) -> None:
    """失败只写一条（每线程复用一行）CrispMirrorLog，绝不抛回请求线程。"""

    text = str(error or "")[:2000]
    try:
        log, created = CrispMirrorLog.objects.get_or_create(
            thread_key=thread_key,
            message_id=INBOUND_LOG_MESSAGE_ID,
            defaults={
                "sender_kind": "inbound",
                "status": CrispMirrorLog.Status.FAILED,
                "error": text,
                "attempts": 1,
            },
        )
        if not created:
            log.sender_kind = "inbound"
            log.status = CrispMirrorLog.Status.FAILED
            log.error = text
            log.attempts += 1
            log.save(update_fields=["sender_kind", "status", "error", "attempts", "updated_at"])
    except Exception:  # noqa: BLE001 - 日志失败也不能影响用户请求
        logger.exception("crisp inbound failure log crashed")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def pull_thread(
    thread_key: str,
    *,
    now: datetime | None = None,
    budget_seconds: float = CALL_BUDGET_SECONDS,
) -> dict:
    """拉一次某个线程的 Crisp 人工回复（节流 + 游标 + 限时，失败静默）。

    返回 ``{"status": pulled|throttled|skipped|unsupported|failed, "imported": int,
    "requested": int, "error": str}``；**任何异常都不会抛给调用方**。
    """

    thread_key = str(thread_key or "").strip()
    result = {"status": STATUS_SKIPPED, "imported": 0, "requested": 0, "error": ""}
    if not thread_key:
        return result
    target = _resolve_target(thread_key)
    if target is None:
        return result
    # 没配置凭据 / 还没建过 Crisp 会话：没有可拉的东西，也不该消耗配额。
    if not crisp_mirror.is_configured():
        return result
    mirror_session = CrispMirrorSession.objects.filter(thread_key=thread_key).first()
    if mirror_session is None:
        return result

    current = now or timezone.now()
    claimed, reason = _claim_throttle_slot(target, current)
    if not claimed:
        return {**result, "status": STATUS_THROTTLED, "reason": reason}

    window_start_ms = int((current - timedelta(hours=FIRST_PULL_WINDOW_HOURS)).timestamp() * 1000)
    cursor_ms = target.obj.inbound_cursor_ms
    after_ms = int(cursor_ms) if cursor_ms else window_start_ms
    imported = 0
    requested = 0

    try:
        response = _get_messages(mirror_session.session_id, after_ms, budget_seconds)
        items = response.get("data") if isinstance(response, dict) else None
        if isinstance(items, list) and items:
            requested = len(items)
            imported = _import_messages(target, items, mirror_session.session_id)
            advanced = _max_timestamp_ms(items, after_ms)
            if advanced > after_ms:
                _advance_cursor(target, advanced)
    except Exception as exc:  # noqa: BLE001 - 入站失败绝不能影响用户请求
        logger.warning(
            "crisp inbound pull failed",
            extra={"event": "crisp_inbound_failed", "thread_key": thread_key},
        )
        _log_failure(thread_key, f"{type(exc).__name__}: {exc}")
        return {
            "status": STATUS_FAILED,
            "imported": imported,
            "requested": requested,
            "error": str(exc),
        }

    return {
        "status": STATUS_PULLED,
        "imported": imported,
        "requested": requested,
        "error": "",
    }


def pull_support_chat(thread: SupportChatThread, **kwargs) -> dict:
    """买家 ↔ 平台线程的入口（视图里直接用，不用自己拼 thread_key）。"""

    return pull_thread(crisp_mirror.thread_key_for_support_chat(thread), **kwargs)


def pull_conversation(conversation: SupportConversation, **kwargs) -> dict:
    """商家 ↔ 平台会话的入口；其它 kind（历史买家商品咨询）不拉。"""

    if conversation.kind != SupportConversation.Kind.PLATFORM_SUPPORT:
        return {"status": STATUS_UNSUPPORTED, "imported": 0, "requested": 0, "error": ""}
    return pull_thread(crisp_mirror.thread_key_for_conversation(conversation), **kwargs)


def pull_merchant_chat(thread: MerchantChatThread, **kwargs) -> dict:
    """买家 ↔ 商家（``bm:``）线程的入口：客服在 Crisp 的回复回传给买卖双方。

    ``thread`` 必须 ``select_related("buyer", "merchant")``（视图里已经这么查）。
    """

    return pull_thread(crisp_mirror.thread_key_for_merchant_chat(thread), **kwargs)
