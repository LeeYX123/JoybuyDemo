import hashlib
import hmac
import secrets
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
