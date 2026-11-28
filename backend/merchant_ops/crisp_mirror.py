"""Crisp 客服消息镜像（需求 18 / 批次 V）。

自有 ``SupportConversation`` / ``SupportMessage`` 仍是唯一事实源；本模块把商家端、
管理端聊天里「商家 ↔ 系统客服」的消息旁路镜像到 Crisp，让系统客服在 Crisp Inbox
里以统一会话工作。设计约束（见 ``var/crisp_integration_research_20261122/research.md``）：

- ``from=operator`` 无法指定操作者身份，且**客服端 Inbox 不认消息级 ``user.nickname``**
  （只影响访客端 chatbox）→ 客服侧区分靠**会话 meta nickname**（``🟢 买家 ➡️ 🟠 商家ID``
  一类的三段式标题）；消息正文保持干净，不用 ``[商家]``/``[平台]`` 前缀；消息
  ``user.nickname`` 仍传（chatbox 加分项）；
- 会话 ``PATCH .../meta`` 补 ``nickname``/``email``，Inbox 列表不再显示 anonymous；
  历史会话 meta 为空时，下次发消息自动补写一次（进程内缓存，失败只 warning）；
- 2026-11-29 起 meta 还带 **结构化数据**：``data`` = 场景 + 双方 public_id
  （``thread`` / ``scenario`` / ``buyer_id`` / ``merchant_id``），``segments`` =
  场景中文名（Inbox 标签筛选）。实测真实会话 PATCH 后 GET 回读，``data``/``segments``
  均原样保存（无清洗、无需后台预建）；标题口径不变，ID 不再挤在标题里；
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
    MerchantChatMessage,
    MerchantChatThread,
    SupportChatMessage,
    SupportChatThread,
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
# 批次 AA（需求 23.2 / Q8）：``merchant:``（商家 ↔ 平台）线程里商家消息改成
# ``from=user`` + 昵称=店名 —— 该线程的 Crisp 访客本来就是商家，语义正确；
# ``bm:``（买家 ↔ 商家）线程的访客是买家，商家仍用 ``SENDER_MERCHANT``（operator），
# 否则商家会顶替买家的访客身份。
SENDER_MERCHANT_VISITOR = "merchant_visitor"

STATUS_SKIPPED = "skipped"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_DUPLICATE = "duplicate"

# 新会话的第一条 from=user 消息：Crisp 收到它才会把会话推进 Inbox。
SESSION_OPENING_MESSAGE = "Conversation started"
# 平台（系统客服）消息在气泡上显示的昵称；可在 settings/env 用 CRISP_PLATFORM_NICKNAME 覆盖。
DEFAULT_PLATFORM_NICKNAME = "Joybuy 客服"
# Crisp meta nickname 长度未实测，按调研建议本地截断，避免超长被拒。
META_NICKNAME_MAX_LENGTH = 40
# 2026-11-29：Inbox 会话标题改为带角色 emoji 的「左 ➡️ 右」，三个场景都保留双方
# 身份：买家在左用 🟢、商家在左（merchant: 线程）用 🟠，中间 `` ➡️ ``（前后各一空格）。
# 平台侧在**标题**里固定写「JoyBuy客服」（注意大小写、且**不加 emoji**）——它与消息
# 气泡上的 ``CRISP_PLATFORM_NICKNAME``（默认「Joybuy 客服」）是两个口径，不要合并/复用。
# 注意 ``➡️`` 是 U+27A1 + U+FE0F 两个码位，``len()`` 算 2；截断只动名字，emoji/箭头
# 属于固定部分，永远完整保留。
META_EMOJI_BUYER = "🟢"
META_EMOJI_MERCHANT = "🟠"
META_TITLE_ARROW = "➡️"
META_TITLE_PLATFORM_NAME = "JoyBuy客服"
# 名牌缺失时的退化名：避免出现「🟢  ➡️ JoyBuy客服」这种空头标题。
META_TITLE_BUYER_FALLBACK = "买家"
META_TITLE_MERCHANT_FALLBACK = "商家"
# 标题里「左右两侧分别是谁」：决定 emoji 前缀。平台侧无 emoji。
META_TITLE_ROLE_BUYER = "buyer"
META_TITLE_ROLE_MERCHANT = "merchant"
META_TITLE_ROLE_PLATFORM = "platform"

# 会话 meta.data 里的线程类型（与 ``thread_key`` 前缀一致）与中文场景名。
# ``segments`` 用同一个场景名（Inbox 标签筛选）。三种场景固定，不新增。
META_THREAD_BUYER_PLATFORM = "bp"
META_THREAD_BUYER_MERCHANT = "bm"
META_THREAD_MERCHANT_PLATFORM = "merchant"
SCENARIO_BUYER_PLATFORM = "买家咨询平台"
SCENARIO_BUYER_MERCHANT = "买家咨询商家"
SCENARIO_MERCHANT_PLATFORM = "商家咨询平台"


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
        "platform_nickname": platform_nickname(),
    }


def platform_nickname() -> str:
    """平台客服消息的显示名（settings.CRISP_PLATFORM_NICKNAME，默认「Joybuy 客服」）。"""

    value = (getattr(settings, "CRISP_PLATFORM_NICKNAME", "") or "").strip()
    return value or DEFAULT_PLATFORM_NICKNAME


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


def _http_request(
    method: str, path: str, payload: dict | None, timeout: float | None = None
) -> dict:
    """向 Crisp 发一次 REST 请求；所有网络/协议错误统一抛 CrispRequestError。

    抽成单一函数便于测试 mock（测试绝不真连 Crisp）。``timeout`` 供入站同步
    （``crisp_inbound``）按请求线程预算收紧，默认仍用 ``REQUEST_TIMEOUT_SECONDS``。
    """

    identifier, key, tier = _credentials()
    token = base64.b64encode(f"{identifier}:{key}".encode()).decode()
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(API_BASE_URL + path, data=body, method=method)
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("X-Crisp-Tier", tier)
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(
            request, timeout=timeout or REQUEST_TIMEOUT_SECONDS
        ) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # 把 Crisp 返回的错误体摘要带进异常：排查 401/403 时必须看到 reason。
        raise CrispRequestError(f"{method} {path} -> HTTP {exc.code}{_error_detail(exc)}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CrispRequestError(f"{method} {path} -> {exc}") from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise CrispRequestError(f"{method} {path} -> invalid JSON response") from exc


def _http_post(path: str, payload: dict | None) -> dict:
    return _http_request("POST", path, payload)


def _http_patch(path: str, payload: dict | None) -> dict:
    return _http_request("PATCH", path, payload)


def _http_get(path: str, payload: dict | None = None) -> dict:
    # ``payload`` 只是为了满足 ``_request_with_retry`` 的统一调用约定 ``send(path, payload)``。
    # 批次 AA 修：这个签名以前只有 ``path``，``_get_with_retry`` 传两个参数会抛 TypeError，
    # 导致"已存在会话"的补写 meta 分支一进来就崩，后续消息全部不再镜像（只在真机才复现，
    # 测试里 ``_http_get`` 一直被 mock，所以没暴露）。
    return _http_request("GET", path, None)


def _request_with_retry(method: str, send, path: str, payload: dict | None) -> dict:
    """1 次同步尝试 + 最多 1 次重试；两次都失败才抛 CrispRequestError。

    ``send`` 是单次发送函数（``_http_post`` / ``_http_patch``），单独传入便于测试 mock。
    """

    last_error: CrispRequestError | None = None
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        try:
            return send(path, payload)
        except CrispRequestError as exc:
            last_error = exc
            if attempt < MAX_HTTP_ATTEMPTS and RETRY_DELAY_SECONDS:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_error if last_error else CrispRequestError(f"{method} {path} failed")


def _post_with_retry(path: str, payload: dict | None) -> dict:
    return _request_with_retry("POST", _http_post, path, payload)


def _patch_with_retry(path: str, payload: dict | None) -> dict:
    return _request_with_retry("PATCH", _http_patch, path, payload)


def _get_with_retry(path: str) -> dict:
    return _request_with_retry("GET", _http_get, path, None)


def _conversation_path(session_id: str) -> str:
    return f"/website/{crisp_config()['website_id']}/conversation/{session_id}/message"


def _conversation_meta_path(session_id: str) -> str:
    return f"/website/{crisp_config()['website_id']}/conversation/{session_id}/meta"


def _extract_session_id(response: dict) -> str:
    data = response.get("data") if isinstance(response, dict) else None
    if isinstance(data, dict):
        return str(data.get("session_id") or "").strip()
    return ""


def patch_conversation_meta(
    session_id: str,
    nickname: str = "",
    email: str = "",
    data: dict | None = None,
    segments: list[str] | None = None,
) -> bool:
    """给 Crisp 会话补 ``nickname``/``email``/``data``/``segments``。

    只把**有值**的键放进请求体（空字符串/空 dict/空列表一律不带，避免把 Crisp
    已存的值清空）。``data`` 是结构化元数据（场景 + 双方 public_id），``segments``
    是 Inbox 标签；实测两者都会被原样保存。

    失败只记 warning、返回 False，绝不影响后续发消息（Inbox 仍能用，只是缺元数据）。
    """

    body: dict = {}
    nickname = (nickname or "").strip()[:META_NICKNAME_MAX_LENGTH]
    if nickname:
        body["nickname"] = nickname
    email = (email or "").strip()
    if email:
        body["email"] = email
    if isinstance(data, dict) and data:
        body["data"] = dict(data)
    if segments:
        cleaned = [str(item).strip() for item in segments if str(item).strip()]
        if cleaned:
            body["segments"] = cleaned
    if not body:
        return False

    try:
        _patch_with_retry(_conversation_meta_path(session_id), body)
    except CrispRequestError as exc:
        logger.warning(
            "crisp conversation meta patch failed",
            extra={"event": "crisp_meta_patch_failed", "session_id": session_id},
        )
        logger.debug("crisp meta patch error: %s", exc)
        return False
    return True


def fetch_conversation_meta(session_id: str) -> dict | None:
    """读会话 meta；失败只记 warning 并返回 None（不阻塞发消息）。"""

    try:
        response = _get_with_retry(_conversation_meta_path(session_id))
    except CrispRequestError as exc:
        logger.warning(
            "crisp conversation meta fetch failed",
            extra={"event": "crisp_meta_fetch_failed", "session_id": session_id},
        )
        logger.debug("crisp meta fetch error: %s", exc)
        return None
    data = response.get("data") if isinstance(response, dict) else None
    return data if isinstance(data, dict) else None


# 本进程内 meta 已补全（nickname + data + segments）的会话：历史会话只补一次，
# 避免每条消息都 GET。补写失败不进集合，下次发消息再试。
_META_READY: set[str] = set()


def _meta_data_complete(meta: dict, data: dict, segments: list[str] | None) -> bool:
    """meta 里的 ``data``（以及有场景时的 ``segments``）是否已经写过。"""

    existing_data = meta.get("data")
    if not isinstance(existing_data, dict) or not existing_data:
        return False
    if segments:
        existing_segments = meta.get("segments")
        if not existing_segments:
            return False
    return True


def _backfill_conversation_meta(
    session_id: str,
    nickname: str,
    email: str = "",
    data: dict | None = None,
    segments: list[str] | None = None,
) -> bool:
    """历史会话 meta 缺内容时补写（幂等）：先 GET，只补缺的部分再 PATCH。

    2026-11-29 起不再只看 nickname：``nickname`` 已有但 ``data``/``segments`` 缺失
    时也补一次（老会话都在这一批里）。结果缓存到本进程的 ``_META_READY``（语义 =
    nickname + data + segments 都已就绪）：无缺项或补写成功后不再重复读。
    GET/PATCH 失败都不抛出（只 warning），下次发消息时再试。
    """

    if session_id in _META_READY:
        return False
    wants_nickname = bool((nickname or "").strip())
    wants_data = bool(data)
    if not wants_nickname and not wants_data:
        return False
    meta = fetch_conversation_meta(session_id)
    if meta is None:
        return False

    body: dict = {}
    if wants_nickname and not (meta.get("nickname") or "").strip():
        body["nickname"] = nickname
        if (email or "").strip():
            body["email"] = email
    if wants_data and not _meta_data_complete(meta, data, segments):
        body["data"] = data
        if segments:
            body["segments"] = segments
    if not body:
        _META_READY.add(session_id)
        return False
    if patch_conversation_meta(session_id, **body):
        _META_READY.add(session_id)
        return True
    return False


def ensure_session(
    thread_key: str,
    nickname: str = "",
    occurred_at: datetime | None = None,
    email: str = "",
    data: dict | None = None,
    segments: list[str] | None = None,
) -> str:
    """取（或首次创建）线程对应的 Crisp 会话 id。

    首次创建顺序：``POST /conversation`` → 落库映射 → ``PATCH .../meta``（会话昵称/
    邮箱/结构化数据/标签）→ 发一条 ``from=user`` 的「Conversation started」。先落库
    再发首消息，避免首消息失败后重试又建一个会话。``occurred_at`` 用于把开场消息时间
    排在正式消息之前（Inbox 列表取最新一条做预览）。

    会话已存在时只做一次「meta 缺什么补什么」检查（历史会话是 anonymous / 无 data 的）。
    """

    existing = CrispMirrorSession.objects.filter(thread_key=thread_key).first()
    if existing is not None:
        _backfill_conversation_meta(
            existing.session_id, nickname, email, data=data, segments=segments
        )
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

    # 先补 meta 再发首消息：Inbox 里一出现会话就带昵称/场景标签（失败仅记日志，不阻塞）。
    if patch_conversation_meta(
        session_id, nickname=nickname, email=email, data=data, segments=segments
    ):
        _META_READY.add(session_id)

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
    """构造 Crisp 消息体。

    发送方身份统一由消息级 ``user.nickname`` 表达（实测 operator 消息也会被 Crisp
    原样保留并在气泡上显示），正文不再带 ``[商家]``/``[平台]`` 前缀。
    """

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
        payload["content"] = body
        payload["user"] = {"type": "website", "nickname": sender_name or "商家"}
    elif sender_kind == SENDER_MERCHANT_VISITOR:
        # ``merchant:`` 线程：商家就是该 Crisp 会话的访客（Q8），平台客服仍是 operator。
        payload["from"] = SENDER_USER
        payload["content"] = body
        payload["user"] = {"type": "website", "nickname": sender_name or "商家"}
    elif sender_kind == SENDER_PLATFORM:
        payload["from"] = "operator"
        payload["content"] = body
        payload["user"] = {"type": "website", "nickname": platform_nickname()}
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
    session_nickname: str = "",
    session_email: str = "",
    session_data: dict | None = None,
    session_segments: list[str] | None = None,
) -> dict:
    """把一条聊天消息镜像到 Crisp（幂等、失败不抛异常）。

    ``session_nickname``/``session_email``/``session_data``/``session_segments`` 只用于
    会话 meta：首次建会话时一次写入；已有会话仅在缺失时补写一次（见
    ``_backfill_conversation_meta``）。``session_data`` 是场景 + 双方 public_id。

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
            # 开场 from=user 消息的访客名（同时作为 meta 昵称的兜底）。
            nickname=(session_nickname or _opening_nickname(sender_kind, sender_name)),
            occurred_at=occurred_at,
            email=session_email,
            data=session_data,
            segments=session_segments,
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
    if sender_kind in {SENDER_MERCHANT, SENDER_MERCHANT_VISITOR}:
        return sender_name or "商家"
    if sender_kind == SENDER_PLATFORM:
        # 与平台消息气泡上的昵称保持一致。
        return platform_nickname()
    return sender_name or "访客"


def thread_key_for_conversation(conversation: SupportConversation) -> str:
    """同一商家的平台客服消息共用一个 Crisp 会话（商家/平台两侧都落这里）。"""

    return f"merchant:{conversation.merchant.public_id}"


def merchant_platform_meta_nickname(merchant) -> str:
    """``merchant:`` 线程的 Inbox 会话标题：``🟠 {商家ID} ➡️ JoyBuy客服``。

    商家侧用 ``Merchant.public_id``（不展示店名），取不到 ID 时退化「商家」；
    平台侧固定「JoyBuy客服」且不带 emoji。
    """

    return build_session_title(
        merchant_title_name(merchant),
        META_TITLE_PLATFORM_NAME,
        left_role=META_TITLE_ROLE_MERCHANT,
        right_role=META_TITLE_ROLE_PLATFORM,
    )


# ---------------------------------------------------------------------------
# 会话 meta 结构化数据（2026-11-29）
#
# 用户口径：**标题保持现状**（不把双方 ID 塞进标题），场景与双方 ID 收进
# ``meta.data``，场景同时写入 ``meta.segments`` 供 Inbox 标签筛选：
#
#   data = {"thread": "bp|bm|merchant", "scenario": "<中文场景>",
#           "buyer_id": "JYU…", "merchant_id": "JYM…"}
#
# 四个键**始终齐全**，不适用的一侧留空串（``merchant:`` 线程没有买家）。
# 真实 Crisp 实测：PATCH 后 GET 回读 ``data``/``segments`` 原样保存。
# ---------------------------------------------------------------------------
def public_id_of(instance) -> str:
    """取 ``public_id``（``JYU…`` / ``JYM…``）；对象缺失或字段为空时返回空串。"""

    return str(getattr(instance, "public_id", "") or "").strip()


def build_meta_data(
    thread: str, scenario: str, buyer=None, merchant=None
) -> dict:
    """拼 ``meta.data``：场景 + 双方 public_id（不适用的一侧为空串）。"""

    return {
        "thread": thread,
        "scenario": scenario,
        "buyer_id": public_id_of(buyer),
        "merchant_id": public_id_of(merchant),
    }


def meta_segments(scenario: str) -> list[str]:
    """场景名同时作为 Inbox 标签（``meta.segments``）；空场景不打标签。"""

    scenario = (scenario or "").strip()
    return [scenario] if scenario else []


def support_chat_meta_data(thread) -> dict:
    """``bp:``（买家 ↔ 平台客服）：只有买家，``merchant_id`` 留空。"""

    return build_meta_data(
        META_THREAD_BUYER_PLATFORM,
        SCENARIO_BUYER_PLATFORM,
        buyer=getattr(thread, "buyer", None),
    )


def merchant_chat_meta_data(thread) -> dict:
    """``bm:``（买家 ↔ 商家）：双方 public_id 都有。"""

    return build_meta_data(
        META_THREAD_BUYER_MERCHANT,
        SCENARIO_BUYER_MERCHANT,
        buyer=getattr(thread, "buyer", None),
        merchant=getattr(thread, "merchant", None),
    )


def merchant_platform_meta_data(merchant) -> dict:
    """``merchant:``（商家 ↔ 平台客服）：该线程没有买家，``buyer_id`` 留空。"""

    return build_meta_data(
        META_THREAD_MERCHANT_PLATFORM,
        SCENARIO_MERCHANT_PLATFORM,
        merchant=merchant,
    )


def queue_support_message_mirror(message: SupportMessage) -> None:
    """商家端/管理端聊天消息落库后调用：事务提交后再镜像，且绝不影响接口返回。

    只镜像 ``PLATFORM_SUPPORT``（商家 ↔ 系统客服）。买家咨询属于「用户 ↔ 商家」，
    走 ``queue_merchant_chat_mirror``。
    """

    conversation = message.conversation
    if conversation.kind != SupportConversation.Kind.PLATFORM_SUPPORT:
        return
    if message.sender == SupportMessage.Sender.MERCHANT:
        # 批次 AA（Q8）：merchant: 线程的访客是商家 → from=user + 昵称=店名。
        sender_kind = SENDER_MERCHANT_VISITOR
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
        # 这条线程的「访客」是商家：会话 meta 标题 = 「🟠 商家ID ➡️ JoyBuy客服」
        # （2026-11-29 口径：商家显示 public_id，不展示店名），Inbox 列表不再 anonymous。
        "session_nickname": merchant_platform_meta_nickname(conversation.merchant),
        # 结构化元数据：该线程没有买家，buyer_id 留空；场景打 Inbox 标签。
        "session_data": merchant_platform_meta_data(conversation.merchant),
        "session_segments": meta_segments(SCENARIO_MERCHANT_PLATFORM),
    }

    def _run() -> None:
        try:
            mirror_message(**payload)
        except Exception:  # noqa: BLE001 - 镜像失败绝不能让 on_commit 抛回请求
            logger.exception(
                "crisp mirror crashed", extra={"event": "crisp_mirror_crashed"}
            )

    transaction.on_commit(_run)


def thread_key_for_merchant_chat(thread) -> str:
    """买家 ↔ 商家一对一会话的 Crisp 线程标识（需求 19.2）。

    每个 (买家, 商家) 组合一条独立 Crisp 会话，系统客服在 Inbox 里看到完整往来。
    """

    return f"bm:{thread.buyer.public_id}:{thread.merchant.public_id}"


def merchant_chat_buyer_name(buyer) -> str:
    """Crisp 访客昵称：买家昵称 → 邮箱前缀 → 「买家」。"""

    name = (buyer.display_name or "").strip()
    if name:
        return name
    email = (buyer.email or "").strip()
    if email:
        return email.split("@")[0]
    return "买家"


def _title_role_prefix(role: str) -> str:
    """角色 emoji 前缀（``🟢 `` / ``🟠 ``）；平台侧不带 emoji，返回空串。"""

    if role == META_TITLE_ROLE_BUYER:
        return f"{META_EMOJI_BUYER} "
    if role == META_TITLE_ROLE_MERCHANT:
        return f"{META_EMOJI_MERCHANT} "
    return ""


def _title_role_fallback(role: str) -> str:
    """名牌为空时的退化名：买家 → 「买家」，商家 → 「商家」。"""

    if role == META_TITLE_ROLE_MERCHANT:
        return META_TITLE_MERCHANT_FALLBACK
    return META_TITLE_BUYER_FALLBACK


def merchant_title_name(merchant) -> str:
    """标题里的商家身份用 ``Merchant.public_id``（``JYM`` + 10 位），不展示店名。

    2026-11-29 用户口径：Crisp 会话标题里商家统一显示 ID（店名可能重名/改名）。
    取不到 ID（商家对象缺失或字段为空）时退化「商家」，绝不返回空串。
    """

    public_id = str(getattr(merchant, "public_id", "") or "").strip()
    return public_id or META_TITLE_MERCHANT_FALLBACK


def build_session_title(
    left_name: str,
    right_name: str,
    left_role: str = META_TITLE_ROLE_BUYER,
    right_role: str = META_TITLE_ROLE_MERCHANT,
) -> str:
    """拼 Crisp Inbox 会话标题：``{左emoji} 左名 ➡️ {右emoji} 右名``。

    例：``🟢 小明 ➡️ 🟠 JYMWMRIH9DQQJ`` / ``🟢 小明 ➡️ JoyBuy客服`` /
    ``🟠 JYMWMRIH9DQQJ ➡️ JoyBuy客服``（平台侧无 emoji；商家侧显示 public_id）。
    角色前缀与箭头是**固定部分**，
    超长（``META_NICKNAME_MAX_LENGTH`` = 40）时**优先截左侧名字**，右侧角色名与两侧
    emoji/箭头完整保留——否则会出现「JYMWMRIH9DQQJ ➡️ JoyBuy客」这种半截后缀。只有
    右侧自身就超过 40 字时才截右侧名字（其 emoji 前缀仍保留），左侧保留 1 字。
    """

    left = (left_name or "").strip()
    right = (right_name or "").strip()
    left_prefix = _title_role_prefix(left_role)
    right_prefix = _title_role_prefix(right_role)
    fallback = _title_role_fallback(left_role)
    if not right:
        return f"{left_prefix}{left or fallback}"[:META_NICKNAME_MAX_LENGTH]
    separator = f" {META_TITLE_ARROW} "
    right_label = f"{right_prefix}{right}"
    room = META_NICKNAME_MAX_LENGTH - len(left_prefix) - len(separator) - len(right_label)
    if room >= 1:
        head = left[:room] if left else fallback
        return f"{left_prefix}{head}{separator}{right_label}"
    head = (left or fallback)[:1]
    tail_room = max(
        META_NICKNAME_MAX_LENGTH
        - len(left_prefix)
        - len(head)
        - len(separator)
        - len(right_prefix),
        0,
    )
    return f"{left_prefix}{head}{separator}{right_prefix}{right[:tail_room]}"


def merchant_chat_meta_nickname(thread) -> str:
    """Inbox 会话标题：``🟢 {买家昵称} ➡️ 🟠 {商家ID}``。

    客服端 Inbox 的 operator 气泡只显示席位账号（不认 ``user.nickname``），所以把
    「哪位买家 + 哪家店」放进会话 meta nickname，客服靠列表标题区分。商家侧用
    ``Merchant.public_id``（不展示店名），取不到 ID 时退化为「商家」，不会出现空头标题。
    """

    buyer_name = merchant_chat_buyer_name(thread.buyer)
    merchant_name = merchant_title_name(thread.merchant)
    return build_session_title(
        buyer_name,
        merchant_name,
        left_role=META_TITLE_ROLE_BUYER,
        right_role=META_TITLE_ROLE_MERCHANT,
    )


def queue_merchant_chat_mirror(message: MerchantChatMessage) -> None:
    """买家 ↔ 商家消息落库后调用：事务提交后镜像到 Crisp，并回写 ``crisp_status``。

    失败/未配置都不影响消息本身（沿用批次 V 口径）：``mirror_message`` 已把异常
    吞掉并写 ``CrispMirrorLog``，这里只做兜底，绝不把异常抛回请求。
    """

    thread = (
        MerchantChatThread.objects.select_related("buyer", "merchant")
        .filter(pk=message.thread_id)
        .first()
    )
    if thread is None:
        return
    if message.sender_kind == MerchantChatMessage.SenderKind.BUYER:
        sender_kind = SENDER_USER
        sender_name = merchant_chat_buyer_name(thread.buyer)
    elif message.sender_kind == MerchantChatMessage.SenderKind.MERCHANT:
        sender_kind = SENDER_MERCHANT
        sender_name = thread.merchant.display_name
    else:
        return

    thread_key = thread_key_for_merchant_chat(thread)
    payload = {
        "thread_key": thread_key,
        "sender_kind": sender_kind,
        "sender_name": sender_name,
        "body": message.body,
        "occurred_at": message.created_at,
        "message_id": str(message.pk),
        # Inbox 会话标题：买家昵称-->店名（客服端只认这个，不认消息 user.nickname）；
        # 有邮箱一并带上（Crisp 可能不保存，失败不影响消息）。
        "session_nickname": merchant_chat_meta_nickname(thread),
        "session_email": (thread.buyer.email or "").strip(),
        # 结构化元数据：bm 线程买家与商家都在，双方 public_id 都带上。
        "session_data": merchant_chat_meta_data(thread),
        "session_segments": meta_segments(SCENARIO_BUYER_MERCHANT),
    }
    message_pk = message.pk

    def _run() -> None:
        try:
            result = mirror_message(**payload)
            status = result.get("status")
            if status == STATUS_DUPLICATE:
                status = STATUS_SENT
            if status in {STATUS_SENT, STATUS_SKIPPED, STATUS_FAILED}:
                MerchantChatMessage.objects.filter(pk=message_pk).update(crisp_status=status)
        except Exception:  # noqa: BLE001 - 镜像失败绝不能让 on_commit 抛回请求
            logger.exception(
                "merchant chat crisp mirror crashed",
                extra={"event": "merchant_chat_crisp_mirror_crashed"},
            )

    transaction.on_commit(_run)


def thread_key_for_support_chat(thread) -> str:
    """买家 ↔ 平台客服会话的 Crisp 线程标识（需求 21.3-1）。

    每个买家一条独立 Crisp 会话：``bp:{buyer_public_id}``，与 ``bm:``（买家 ↔ 商家）
    和 ``merchant:``（商家 ↔ 平台）完全隔离。
    """

    return f"bp:{thread.buyer.public_id}"


def support_chat_meta_nickname(thread) -> str:
    """Inbox 会话标题 = ``🟢 {买家昵称} ➡️ JoyBuy客服``（客服端只认 meta nickname）。

    买家 ↔ 平台没有「店名」维度，右侧固定写平台客服名「JoyBuy客服」（不带 emoji）；
    客服回复时标题也不变（仍以买家名开头）。
    """

    return build_session_title(
        merchant_chat_buyer_name(thread.buyer),
        META_TITLE_PLATFORM_NAME,
        left_role=META_TITLE_ROLE_BUYER,
        right_role=META_TITLE_ROLE_PLATFORM,
    )


def queue_support_chat_mirror(message: SupportChatMessage) -> None:
    """买家 ↔ 平台客服消息落库后调用：事务提交后镜像，并回写 ``crisp_status``。

    口径与批次 V/W 一致：买家 → ``from=user`` + 买家昵称；客服 → ``from=operator``
    （``user.nickname`` = ``CRISP_PLATFORM_NICKNAME``）；正文无前缀；会话 meta 标题
    始终是 ``{买家昵称}-->JoyBuy客服``（即使客服先回复也不改）。失败/未配置都不影响
    已落库消息。
    """

    thread = SupportChatThread.objects.select_related("buyer").filter(pk=message.thread_id).first()
    if thread is None:
        return
    if message.sender_kind == SupportChatMessage.SenderKind.BUYER:
        sender_kind = SENDER_USER
        sender_name = merchant_chat_buyer_name(thread.buyer)
    elif message.sender_kind == SupportChatMessage.SenderKind.SUPPORT:
        sender_kind = SENDER_PLATFORM
        sender_name = platform_nickname()
    else:
        return

    payload = {
        "thread_key": thread_key_for_support_chat(thread),
        "sender_kind": sender_kind,
        "sender_name": sender_name,
        "body": message.body,
        "occurred_at": message.created_at,
        "message_id": str(message.pk),
        # Inbox 会话标题：始终买家昵称（客服端只认这个）。
        "session_nickname": support_chat_meta_nickname(thread),
        "session_email": (thread.buyer.email or "").strip(),
        # 结构化元数据：bp 线程只有买家，merchant_id 留空。
        "session_data": support_chat_meta_data(thread),
        "session_segments": meta_segments(SCENARIO_BUYER_PLATFORM),
    }
    message_pk = message.pk

    def _run() -> None:
        try:
            result = mirror_message(**payload)
            status = result.get("status")
            if status == STATUS_DUPLICATE:
                status = STATUS_SENT
            if status in {STATUS_SENT, STATUS_SKIPPED, STATUS_FAILED}:
                SupportChatMessage.objects.filter(pk=message_pk).update(crisp_status=status)
        except Exception:  # noqa: BLE001 - 镜像失败绝不能让 on_commit 抛回请求
            logger.exception(
                "support chat crisp mirror crashed",
                extra={"event": "support_chat_crisp_mirror_crashed"},
            )

    transaction.on_commit(_run)
