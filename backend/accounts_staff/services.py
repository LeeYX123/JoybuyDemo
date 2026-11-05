import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts_staff.domain import TotpInvalid, TotpNotEnrolled, TotpReplay
from accounts_staff.models import StaffAccount, StaffSession, StaffTotpDevice


def _hmac_digest(secret: str, namespace: str, value: str) -> str:
    message = f"{namespace}:{value}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def session_token_digest(token: str) -> str:
    return _hmac_digest(settings.STAFF_SESSION_HMAC_KEY, "staff-session", token)


def _fernet() -> Fernet:
    derived_key = hashlib.sha256(settings.STAFF_TOTP_ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived_key))


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_totp_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, counter: int) -> str:
    padded_secret = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def current_totp_code(secret: str, timestamp: int | None = None) -> str:
    effective_time = int(time.time()) if timestamp is None else timestamp
    return totp_code(secret, effective_time // settings.STAFF_TOTP_PERIOD_SECONDS)


def provision_totp_device(staff: StaffAccount) -> tuple[StaffTotpDevice, str, str]:
    secret = generate_totp_secret()
    device, _ = StaffTotpDevice.objects.update_or_create(
        staff=staff,
        defaults={
            "secret_ciphertext": encrypt_totp_secret(secret),
            "confirmed_at": timezone.now(),
            "disabled_at": None,
            "last_verified_counter": None,
        },
    )
    label = quote(f"Joybuy:{staff.email}")
    issuer = quote("Joybuy")
    uri = (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        f"&period={settings.STAFF_TOTP_PERIOD_SECONDS}&digits=6"
    )
    return device, secret, uri


def verify_totp(staff: StaffAccount, code: str, timestamp: int | None = None) -> None:
    effective_time = int(time.time()) if timestamp is None else timestamp
    current_counter = effective_time // settings.STAFF_TOTP_PERIOD_SECONDS
    error = None

    with transaction.atomic():
        device = (
            StaffTotpDevice.objects.select_for_update()
            .filter(staff=staff, disabled_at__isnull=True)
            .first()
        )
        if device is None:
            error = TotpNotEnrolled()
        else:
            secret = decrypt_totp_secret(device.secret_ciphertext)
            matched_counter = None
            for counter in range(
                current_counter - settings.STAFF_TOTP_ALLOWED_DRIFT_STEPS,
                current_counter + settings.STAFF_TOTP_ALLOWED_DRIFT_STEPS + 1,
            ):
                if hmac.compare_digest(totp_code(secret, counter), code):
                    matched_counter = counter
                    break
            if matched_counter is None:
                error = TotpInvalid()
            elif (
                device.last_verified_counter is not None
                and matched_counter <= device.last_verified_counter
            ):
                error = TotpReplay()
            else:
                device.last_verified_counter = matched_counter
                device.save(update_fields=["last_verified_counter", "updated_at"])

    if error:
        raise error


def create_staff_session(
    *, staff: StaffAccount, ip_address: str | None, user_agent: str, totp_verified: bool
) -> tuple[str, StaffSession]:
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    session = StaffSession.objects.create(
        staff=staff,
        token_digest=session_token_digest(token),
        expires_at=now + timedelta(seconds=settings.STAFF_SESSION_MAX_AGE_SECONDS),
        last_seen_at=now,
        totp_verified_at=now if totp_verified else None,
        ip_address=ip_address,
        user_agent=user_agent[:512],
    )
    return token, session


def resolve_staff_session(token: str) -> StaffSession | None:
    now = timezone.now()
    session = (
        StaffSession.objects.select_related("staff")
        .filter(
            token_digest=session_token_digest(token),
            revoked_at__isnull=True,
            expires_at__gt=now,
            staff__status=StaffAccount.Status.ACTIVE,
        )
        .first()
    )
    if session and session.last_seen_at < now - timedelta(minutes=5):
        StaffSession.objects.filter(pk=session.pk).update(last_seen_at=now)
        session.last_seen_at = now
    return session


def revoke_staff_session(session: StaffSession | None) -> None:
    if session and session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])


def set_staff_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=settings.STAFF_SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.STAFF_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
        path=settings.STAFF_SESSION_COOKIE_PATH,
    )


def delete_staff_session_cookie(response) -> None:
    response.delete_cookie(
        key=settings.STAFF_SESSION_COOKIE_NAME,
        path=settings.STAFF_SESSION_COOKIE_PATH,
        samesite="Lax",
    )
    # 兼容历史 Cookie（旧作用域 /api/v1/admin/），避免退出后仍有同名残留。
    for legacy_path in getattr(settings, "STAFF_SESSION_COOKIE_LEGACY_PATHS", ()):
        response.delete_cookie(
            key=settings.STAFF_SESSION_COOKIE_NAME,
            path=legacy_path,
            samesite="Lax",
        )


def rate_limit_key(email: str, ip_address: str) -> str:
    fingerprint = _hmac_digest(
        settings.STAFF_SESSION_HMAC_KEY,
        "staff-login-rate-limit",
        f"{email}:{ip_address}",
    )
    return f"staff-rate:login:{fingerprint}"


def rate_limit_reached(key: str) -> bool:
    return int(cache.get(key, 0)) >= settings.STAFF_LOGIN_FAILURE_LIMIT


def increment_rate_limit(key: str) -> int:
    if cache.add(key, 1, timeout=settings.STAFF_LOGIN_FAILURE_WINDOW_SECONDS):
        return 1
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, 1, timeout=settings.STAFF_LOGIN_FAILURE_WINDOW_SECONDS)
        return 1


def clear_rate_limit(key: str) -> None:
    cache.delete(key)


def get_staff_permission_codes(staff: StaffAccount) -> set[str]:
    """员工持有的权限码集合。

    ``X.manage`` 会隐式带上 ``X.view``：A16 规定「操作必须同时具备查看」，
    在读取侧统一补齐，避免每个调用点各判一次。
    """

    codes = set(
        staff.roles.values_list("permissions__code", flat=True).exclude(permissions__code=None)
    )
    for code in list(codes):
        if code.endswith(".manage"):
            codes.add(f"{code[: -len('.manage')]}.view")
    return codes
