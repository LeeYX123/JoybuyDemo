"""Crisp 客服消息镜像（需求 18 / 批次 V）。

自有 ``SupportConversation`` / ``SupportMessage`` 仍是唯一事实源；本模块把商家端、
管理端聊天里「商家 ↔ 系统客服」的消息旁路镜像到 Crisp，让系统客服在 Crisp Inbox
里以统一会话工作。设计约束（见 ``var/crisp_integration_research_20261122/research.md``）：

- ``from=operator`` 无法指定操作者身份 → 商家/平台身份用正文前缀 ``[商家]``/``[平台]``；
- 新建会话后必须有一条 ``from=user`` 的消息才会进 Inbox；
- 建会话无幂等键、无自定义 session_id → ``CrispMirrorSession`` 落库映射；
- 每条消息带 ``fingerprint``（必须是 number：取 ``sha256(thread_key:message_id)`` 前 48 bit），
  Crisp 侧也能据此去重；
- 未配置 token → 返回 ``skipped`` 且不发任何 HTTP（只写一条日志，便于排查）；
- 任何 HTTP 失败都不抛给主流程，写 ``CrispMirrorLog`` 后由后续重试/命令补发。
"""

import base64
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from merchant_ops.models import (
    CrispMirrorLog,
    CrispMirrorSession,
    SupportConversation,
    SupportMessage,
)

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.crisp.chat/v1"
REQUEST_TIMEOUT_SECONDS = 5
# 一次调用最多 2 次 HTTP 尝试（1 次同步 + 1 次重试），避免在请求线程里长时间阻塞。
MAX_HTTP_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5

SENDER_MERCHANT = "merchant"
SENDER_PLATFORM = "platform"
SENDER_USER = "user"

STATUS_SKIPPED = "skipped"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_DUPLICATE = "duplicate"

# 新会话的第一条 from=user 消息：Crisp 收到它才会把会话推进 Inbox。
SESSION_OPENING_MESSAGE = "Conversation started"


class CrispRequestError(RuntimeError):
    """Crisp REST 调用失败（网络错误、非 2xx、响应无法解析）。"""


def crisp_config() -> dict:
    """当前进程读到的 Crisp 配置（settings 启动时从 env 读一次）。"""

    return {
        "website_id": getattr(settings, "CRISP_WEBSITE_ID", "") or "",
        "website_token": getattr(settings, "CRISP_WEBSITE_TOKEN", "") or "",
        "plugin_id": getattr(settings, "CRISP_PLUGIN_ID", "") or "",
        "plugin_token": getattr(settings, "CRISP_PLUGIN_TOKEN", "") or "",
        "api_token_id": getattr(settings, "CRISP_API_TOKEN_ID", "") or "",
        "api_token_key": getattr(settings, "CRISP_API_TOKEN_KEY", "") or "",
        "api_tier": getattr(settings, "CRISP_API_TIER", "") or "website",
    }


def is_configured() -> bool:
    """有 website id + 任一凭据才认为可镜像；缺任意一项都静默跳过。"""

    config = crisp_config()
    if not config["website_id"]:
        return False
    return bool(
        (config["api_token_id"] and config["api_token_key"])
        or config["website_token"]
        or (config["plugin_id"] and config["plugin_token"])
    )


def _credentials() -> tuple[str, str, str]:
    """返回 ``(identifier, key, tier)``。

    优先级：workspace API token > plugin token > website token。API token 的
    identifier/key 即后台「API 令牌」的 identifier + key，tier 由 ``CRISP_API_TIER``
    指定（官网 workspace 令牌用默认 ``website``）。
    """

    config = crisp_config()
    if config["api_token_id"] and config["api_token_key"]:
        return config["api_token_id"], config["api_token_key"], config["api_tier"]
    if config["plugin_id"] and config["plugin_token"]:
        return config["plugin_id"], config["plugin_token"], "plugin"
    return config["website_id"], config["website_token"], "website"


def _error_detail(exc: urllib.error.HTTPError, limit: int = 300) -> str:
    """读取 HTTP 错误响应体（截断），用于 CrispRequestError 文案；读失败不影响主流程。"""

    try:
        body = exc.read() or b""
    except Exception:  # noqa: BLE001 - 读错误体失败只影响文案
        return ""
    text = body.decode("utf-8", "replace").strip().replace("\n", " ")
    if not text:
        return ""
    return f" body={text[:limit]}"


def _http_post(path: str, payload: dict | None) -> dict:
    """向 Crisp 发一次 POST；所有网络/协议错误统一抛 CrispRequestError。

    抽成单一函数便于测试 mock（测试绝不真连 Crisp）。
    """

    identifier, key, tier = _credentials()
    token = base64.b64encode(f"{identifier}:{key}".encode()).decode()
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(API_BASE_URL + path, data=body, method="POST")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("X-Crisp-Tier", tier)
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # 把 Crisp 返回的错误体摘要带进异常：排查 401/403 时必须看到 reason。
        raise CrispRequestError(f"POST {path} -> HTTP {exc.code}{_error_detail(exc)}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CrispRequestError(f"POST {path} -> {exc}") from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise CrispRequestError(f"POST {path} -> invalid JSON response") from exc


def _post_with_retry(path: str, payload: dict | None) -> dict:
    """1 次同步尝试 + 最多 1 次重试；两次都失败才抛 CrispRequestError。"""

    last_error: CrispRequestError | None = None
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        try:
            return _http_post(path, payload)
        except CrispRequestError as exc:
            last_error = exc
            if attempt < MAX_HTTP_ATTEMPTS and RETRY_DELAY_SECONDS:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_error if last_error else CrispRequestError(f"POST {path} failed")


def _conversation_path(session_id: str) -> str:
    return f"/website/{crisp_config()['website_id']}/conversation/{session_id}/message"


def _extract_session_id(response: dict) -> str:
    data = response.get("data") if isinstance(response, dict) else None
    if isinstance(data, dict):
        return str(data.get("session_id") or "").strip()
    return ""


def ensure_session(
    thread_key: str, nickname: str = "", occurred_at: datetime | None = None
) -> str:
    """取（或首次创建）线程对应的 Crisp 会话 id。

    首次创建顺序：``POST /conversation`` → 落库映射 → 发一条 ``from=user`` 的
    「Conversation started」。先落库再发首消息，避免首消息失败后重试又建一个会话。
    ``occurred_at`` 用于把开场消息时间排在正式消息之前（Inbox 列表取最新一条做预览）。
    """

    existing = CrispMirrorSession.objects.filter(thread_key=thread_key).first()
    if existing is not None:
        return existing.session_id

    response = _post_with_retry(f"/website/{crisp_config()['website_id']}/conversation", None)
    session_id = _extract_session_id(response)
    if not session_id:
        raise CrispRequestError("create conversation returned no session_id")

    session, created = CrispMirrorSession.objects.get_or_create(
        thread_key=thread_key, defaults={"session_id": session_id}
    )
    if not created:
        # 并发下别的线程先落库：复用它的会话，丢弃本次刚建的孤儿会话。
        return session.session_id

    when = occurred_at or timezone.now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    opening = {
        "type": "text",
        "from": SENDER_USER,
        "origin": "chat",
        "content": SESSION_OPENING_MESSAGE,
        # 比正式消息早 1s：Crisp Inbox 预览取最新一条，否则开场语会盖住真正的首条消息。
        "timestamp": int(when.timestamp() * 1000) - 1000,
    }
    if nickname:
        opening["user"] = {"type": "website", "nickname": nickname}
    _post_with_retry(_conversation_path(session_id), opening)
    return session_id


def _numeric_fingerprint(thread_key: str, message_id: str) -> int:
    """Crisp 的 ``fingerprint`` 必须是 number（字符串会 400 invalid_data）。

    用 ``sha256(thread_key:message_id)`` 前 48 bit 生成稳定整数：同一本地消息永远得到
    同一个值（Crisp 侧可据此去重），且远小于 JS 安全整数 2^53-1。
    """

    digest = hashlib.sha256(f"{thread_key}:{message_id}".encode()).hexdigest()
    return int(digest[:12], 16)


def build_message_payload(
    sender_kind: str,
    sender_name: str,
    body: str,
    occurred_at: datetime | None,
    thread_key: str,
    message_id: str,
) -> dict:
    """构造 Crisp 消息体：operator 用正文前缀表达身份，user 用 nickname。"""

    when = occurred_at or timezone.now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    payload = {
        "type": "text",
        "origin": "chat",
        "timestamp": int(when.timestamp() * 1000),
        "fingerprint": _numeric_fingerprint(thread_key, message_id),
    }

    if sender_kind == SENDER_MERCHANT:
        payload["from"] = "operator"
        payload["content"] = f"[商家] {sender_name or '商家'}: {body}"
    elif sender_kind == SENDER_PLATFORM:
        payload["from"] = "operator"
        payload["content"] = f"[平台]: {body}"
    elif sender_kind == SENDER_USER:
        payload["from"] = "user"
        payload["content"] = body
        payload["user"] = {"type": "website", "nickname": sender_name or "访客"}
    else:
        raise ValueError(f"unsupported sender_kind: {sender_kind}")
    return payload


def _claim_log(thread_key: str, message_id: str, sender_kind: str) -> tuple[CrispMirrorLog, bool]:
    """取（或创建）投递记录；已 SENT 的记录不再重复发送。"""

    log, created = CrispMirrorLog.objects.get_or_create(
        thread_key=thread_key,
        message_id=message_id,
        defaults={"sender_kind": sender_kind, "status": CrispMirrorLog.Status.PENDING},
    )
    if not created and log.status != CrispMirrorLog.Status.SENT:
        # SKIPPED / FAILED 允许重试：配置补齐或故障恢复后可以补发同一条。
        log.sender_kind = sender_kind
        log.error = ""
        log.save(update_fields=["sender_kind", "error", "updated_at"])
    return log, created


def _mark(log: CrispMirrorLog, status: str, error: str = "", *, bump_attempts: bool) -> None:
    log.status = status
    log.error = error[:2000]
    if bump_attempts:
        log.attempts += 1
    log.save(update_fields=["status", "error", "attempts", "updated_at"])


def mirror_message(
    thread_key: str,
    sender_kind: str,
    sender_name: str,
    body: str,
    occurred_at: datetime | None = None,
    message_id: str = "",
) -> dict:
    """把一条聊天消息镜像到 Crisp（幂等、失败不抛异常）。

    返回 ``{"status": skipped|sent|failed|duplicate, "session_id": str, "error": str}``。
    """

    thread_key = str(thread_key or "").strip()
    if not thread_key:
        raise ValueError("thread_key is required")
    message_id = str(message_id or "").strip() or uuid.uuid4().hex

    log, created = _claim_log(thread_key, message_id, sender_kind)
    if not created and log.status == CrispMirrorLog.Status.SENT:
        return {"status": STATUS_DUPLICATE, "session_id": "", "error": ""}

    if not is_configured():
        # 未配置不是错误：只留一条 skipped 记录，绝不发 HTTP、不写 error 级别日志。
        _mark(log, CrispMirrorLog.Status.SKIPPED, "", bump_attempts=False)
        return {"status": STATUS_SKIPPED, "session_id": "", "error": ""}

    try:
        session_id = ensure_session(
            thread_key,
            nickname=_opening_nickname(sender_kind, sender_name),
            occurred_at=occurred_at,
        )
        payload = build_message_payload(
            sender_kind, sender_name, body, occurred_at, thread_key, message_id
        )
        _post_with_retry(_conversation_path(session_id), payload)
    except CrispRequestError as exc:
        message = str(exc)
        _mark(log, CrispMirrorLog.Status.FAILED, message, bump_attempts=True)
        logger.warning(
            "crisp mirror failed",
            extra={"event": "crisp_mirror_failed", "thread_key": thread_key},
        )
        return {"status": STATUS_FAILED, "session_id": "", "error": message}

    _mark(log, CrispMirrorLog.Status.SENT, "", bump_attempts=True)
    return {"status": STATUS_SENT, "session_id": session_id, "error": ""}


def _opening_nickname(sender_kind: str, sender_name: str) -> str:
    if sender_kind == SENDER_MERCHANT:
        return sender_name or "商家"
    if sender_kind == SENDER_PLATFORM:
        return "系统客服"
    return sender_name or "访客"


def thread_key_for_conversation(conversation: SupportConversation) -> str:
    """同一商家的平台客服消息共用一个 Crisp 会话（商家/平台两侧都落这里）。"""

    return f"merchant:{conversation.merchant.public_id}"


def queue_support_message_mirror(message: SupportMessage) -> None:
    """商家端/管理端聊天消息落库后调用：事务提交后再镜像，且绝不影响接口返回。

    只镜像 ``PLATFORM_SUPPORT``（商家 ↔ 系统客服）。买家咨询属于「用户 ↔ 商家」，
    本轮不做；用户 ↔ 系统客服本身就在 Crisp 原生会话里。
    """

    conversation = message.conversation
    if conversation.kind != SupportConversation.Kind.PLATFORM_SUPPORT:
        return
    if message.sender == SupportMessage.Sender.MERCHANT:
        sender_kind = SENDER_MERCHANT
        sender_name = conversation.merchant.display_name
    elif message.sender == SupportMessage.Sender.PLATFORM:
        sender_kind = SENDER_PLATFORM
        sender_name = message.author_label or "平台客服"
    else:
        return

    thread_key = thread_key_for_conversation(conversation)
    payload = {
        "thread_key": thread_key,
        "sender_kind": sender_kind,
        "sender_name": sender_name,
        "body": message.text,
        "occurred_at": message.created_at,
        "message_id": str(message.pk),
    }

    def _run() -> None:
        try:
            mirror_message(**payload)
        except Exception:  # noqa: BLE001 - 镜像失败绝不能让 on_commit 抛回请求
            logger.exception(
                "crisp mirror crashed", extra={"event": "crisp_mirror_crashed"}
            )

    transaction.on_commit(_run)
