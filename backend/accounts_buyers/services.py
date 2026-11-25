import hashlib
import hmac
import random
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts_buyers.domain import (
    VerificationCodeExpired,
    VerificationCodeInvalid,
    VerificationCodeLocked,
    VerificationDeliveryUnavailable,
)
from accounts_buyers.models import BuyerAccount, BuyerSession, VerificationCode


def _hmac_digest(secret: str, namespace: str, value: str) -> str:
    message = f"{namespace}:{value}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verification_code_digest(target: str, purpose: str, code: str) -> str:
    return _hmac_digest(
        settings.VERIFICATION_CODE_HMAC_KEY,
        "verification-code",
        f"{target}:{purpose}:{code}",
    )


def session_token_digest(token: str) -> str:
    return _hmac_digest(settings.BUYER_SESSION_HMAC_KEY, "buyer-session", token)


def ensure_display_name(account: BuyerAccount) -> str:
    """需求 13.5-6：未设置用户名时生成 `user+4位数字+4位小写字母`（真站格式实证
    user4323txlb），一次生成固定存库；已设置（含用户自改）则原样返回。

    三方登录建的账号可能没有邮箱，展示名只能走这条生成规则，所以逻辑放在 service
    层共用（视图与 `accounts_buyers.oauth` 都调它）。
    """

    if account.display_name:
        return account.display_name
    candidate = ""
    for _ in range(10):
        candidate = "user" + "".join(random.choices(string.digits, k=4)) + "".join(
            random.choices(string.ascii_lowercase, k=4)
        )
        if not BuyerAccount.objects.filter(display_name=candidate).exists():
            break
    account.display_name = candidate
    account.save(update_fields=["display_name", "updated_at"])
    return candidate


def rate_limit_key(scope: str, *values: str) -> str:
    fingerprint = _hmac_digest(
        settings.BUYER_SESSION_HMAC_KEY,
        f"rate-limit:{scope}",
        ":".join(values),
    )
    return f"buyer-rate:{scope}:{fingerprint}"


def increment_rate_limit(key: str, window_seconds: int) -> int:
    if cache.add(key, 1, timeout=window_seconds):
        return 1
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        return 1


def rate_limit_reached(key: str, limit: int) -> bool:
    return int(cache.get(key, 0)) >= limit


def clear_rate_limit(key: str) -> None:
    cache.delete(key)


@transaction.atomic
def issue_verification_code(
    *, channel: str, target: str, purpose: str
) -> tuple[str, VerificationCode]:
    now = timezone.now()
    VerificationCode.objects.filter(
        channel=channel,
        target=target,
        purpose=purpose,
        consumed_at__isnull=True,
    ).update(consumed_at=now)

    code = f"{secrets.randbelow(1_000_000):06d}"
    record = VerificationCode.objects.create(
        channel=channel,
        target=target,
        purpose=purpose,
        code_digest=verification_code_digest(target, purpose, code),
        expires_at=now + timedelta(seconds=settings.VERIFICATION_CODE_TTL_SECONDS),
    )
    return code, record


def consume_verification_code(
    *, channel: str, target: str, purpose: str, code: str
) -> VerificationCode:
    error = None
    with transaction.atomic():
        record = (
            VerificationCode.objects.select_for_update()
            .filter(
                channel=channel,
                target=target,
                purpose=purpose,
                consumed_at__isnull=True,
            )
            .order_by("-created_at", "-pk")
            .first()
        )
        if record is None:
            error = VerificationCodeInvalid()
        else:
            now = timezone.now()
            if record.expires_at <= now:
                error = VerificationCodeExpired()
            elif record.failed_attempts >= settings.VERIFICATION_CODE_MAX_ATTEMPTS:
                error = VerificationCodeLocked()
            else:
                expected = verification_code_digest(target, purpose, code)
                if not hmac.compare_digest(record.code_digest, expected):
                    record.failed_attempts += 1
                    fields = ["failed_attempts"]
                    if record.failed_attempts >= settings.VERIFICATION_CODE_MAX_ATTEMPTS:
                        record.consumed_at = now
                        fields.append("consumed_at")
                    record.save(update_fields=fields)
                    error = VerificationCodeInvalid()
                else:
                    record.consumed_at = now
                    record.save(update_fields=["consumed_at"])

    if error:
        raise error
    return record


def deliver_verification_code(*, channel: str, target: str, code: str) -> None:
    if settings.VERIFICATION_CODE_TEST_MODE:
        return
    if channel == VerificationCode.Channel.EMAIL:
        send_mail(
            subject="Your Joybuy verification code",
            message=f"Your verification code is {code}. It expires soon.",
            from_email=None,
            recipient_list=[target],
        )
        return
    raise VerificationDeliveryUnavailable


def create_buyer_session(
    *, account: BuyerAccount, ip_address: str | None, user_agent: str
) -> tuple[str, BuyerSession]:
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    session = BuyerSession.objects.create(
        account=account,
        token_digest=session_token_digest(token),
        expires_at=now + timedelta(seconds=settings.BUYER_SESSION_MAX_AGE_SECONDS),
        last_seen_at=now,
        ip_address=ip_address,
        user_agent=user_agent[:512],
    )
    return token, session


# --------------------------------------------------------------------------
# 商家端 → 购物端一次性 handoff（2026-11-22）
# --------------------------------------------------------------------------
# 商家端（m.localhost:5174）与购物端（localhost:3000）跨 host：Chromium 会拒绝
# 从 m.localhost 写入的 Domain=.localhost cookie（localhost 是 public-suffix
# 特例），所以不能靠共享 cookie 传递登录态。改为商家端换一次性 token，购物端
# 用自己的同源域名兑换并种 host-only session cookie。
MERCHANT_HANDOFF_CACHE_PREFIX = "merchant-handoff:"
MERCHANT_HANDOFF_TTL_SECONDS = 60


def issue_merchant_handoff_token(*, buyer_id: str) -> str:
    """签发一次性 handoff token（60 秒，存 Django cache）。

    只存买家 public_id，不存任何会话/密码信息；兑换成功即删除。
    """

    token = secrets.token_urlsafe(32)
    cache.set(
        f"{MERCHANT_HANDOFF_CACHE_PREFIX}{token}",
        {"buyer_id": str(buyer_id)},
        timeout=MERCHANT_HANDOFF_TTL_SECONDS,
    )
    return token


def consume_merchant_handoff_token(token: str) -> BuyerAccount | None:
    """兑换并立即删除 token（一次性）。

    不存在 / 已过期 / 已被用过 / cache 不可用 → None（调用方按无效凭证处理）。
    ``cache.delete`` 的返回值表示「本次请求是否真的删掉了 key」，并发双击时
    只有一个请求拿到 True，其余一律按无效 token 处理。
    """

    token = (token or "").strip()
    if not token:
        return None
    key = f"{MERCHANT_HANDOFF_CACHE_PREFIX}{token}"
    try:
        payload = cache.get(key)
    except Exception:  # cache 不可用时降级为「无效凭证」，不把 500 抛给前端
        return None
    if not isinstance(payload, dict) or not payload.get("buyer_id"):
        return None
    try:
        if not cache.delete(key):
            return None
    except Exception:
        return None
    return BuyerAccount.objects.filter(
        public_id=payload["buyer_id"],
        status=BuyerAccount.Status.ACTIVE,
    ).first()


def resolve_buyer_session(token: str) -> BuyerSession | None:
    now = timezone.now()
    session = (
        BuyerSession.objects.select_related("account")
        .filter(
            token_digest=session_token_digest(token),
            revoked_at__isnull=True,
            expires_at__gt=now,
            account__status=BuyerAccount.Status.ACTIVE,
        )
        .first()
    )
    if session and session.last_seen_at < now - timedelta(minutes=5):
        BuyerSession.objects.filter(pk=session.pk).update(last_seen_at=now)
        session.last_seen_at = now
    return session


def revoke_buyer_session(session: BuyerSession | None) -> None:
    if session and session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])


def set_buyer_session_cookie(response, token: str) -> None:
    """写入买家会话 cookie（host-only）。

    不设 ``domain``：cookie 只在收到响应的那个 host 下生效。商家端切换去商城
    走一次性 handoff token，购物端在自己的域名上兑换时才写 cookie，跨 host
    共享 cookie 的写法（Domain=.localhost）已确认会被 Chromium 拒绝。
    """

    response.set_cookie(
        key=settings.BUYER_SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.BUYER_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
        path="/",  # SSR pages need the session cookie on page routes too
    )


def delete_buyer_session_cookie(response) -> None:
    response.delete_cookie(
        key=settings.BUYER_SESSION_COOKIE_NAME,
        path="/",  # SSR pages need the session cookie on page routes too
        samesite="Lax",
    )


# --------------------------------------------------------------------------
# 白名单余额账户（平台管理后台 A13 / A14）
# --------------------------------------------------------------------------


class BuyerWalletError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def record_buyer_wallet_entry(
    *,
    account,
    kind: str,
    amount,
    note: str = "",
    order=None,
    operator_label: str = "",
    idempotency_key: str | None = None,
):
    """写一条买家余额流水并同步余额；幂等键相同即直接返回旧流水。"""

    from decimal import Decimal

    from django.db import transaction
    from django.utils import timezone

    from accounts_buyers.models import BuyerAccount, BuyerWalletEntry

    amount = Decimal(str(amount or 0)).quantize(Decimal("0.0001"))
    if amount == 0:
        raise BuyerWalletError("AMOUNT_REQUIRED", "金额不能为 0。")

    with transaction.atomic():
        if idempotency_key:
            existing = BuyerWalletEntry.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        locked = BuyerAccount.objects.select_for_update().get(pk=account.pk)
        before = locked.balance
        after = (before + amount).quantize(Decimal("0.0001"))
        if after < 0:
            raise BuyerWalletError("INSUFFICIENT_BUYER_BALANCE", "该账号余额不足。")

        entry = BuyerWalletEntry.objects.create(
            account=locked,
            kind=kind,
            amount=amount,
            balance_before=before,
            balance_after=after,
            currency="CNY",
            order=order,
            operator_label=operator_label,
            note=note,
            idempotency_key=idempotency_key,
            occurred_at=timezone.now(),
        )
        locked.balance = after
        locked.save(update_fields=["balance", "updated_at"])
        return entry


def recharge_buyer(account, *, amount, operator_label: str = "", note: str = ""):
    from decimal import Decimal

    from accounts_buyers.models import BuyerWalletEntry

    value = Decimal(str(amount or 0))
    if value <= 0:
        raise BuyerWalletError("AMOUNT_INVALID", "充值金额必须大于 0。")
    if not account.purchase_whitelisted:
        raise BuyerWalletError("NOT_WHITELISTED", "只有启用中的白名单账号可以充值。")
    return record_buyer_wallet_entry(
        account=account,
        kind=BuyerWalletEntry.Kind.RECHARGE,
        amount=value,
        note=note or "平台充值",
        operator_label=operator_label,
    )


def adjust_buyer_balance(account, *, target_balance, operator_label: str = "", note: str = ""):
    from decimal import Decimal

    from accounts_buyers.models import BuyerWalletEntry

    target = Decimal(str(target_balance or 0)).quantize(Decimal("0.0001"))
    if target < 0:
        raise BuyerWalletError("BALANCE_NEGATIVE", "余额不能为负。")
    delta = target - account.balance
    if delta == 0:
        raise BuyerWalletError("NO_CHANGE", "余额未发生变化。")
    return record_buyer_wallet_entry(
        account=account,
        kind=BuyerWalletEntry.Kind.ADJUSTMENT,
        amount=delta,
        note=note or "平台调整余额",
        operator_label=operator_label,
    )
