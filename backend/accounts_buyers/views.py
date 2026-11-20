import random
import string

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts_buyers.api_exceptions import BuyerApiError
from accounts_buyers.domain import (
    VerificationCodeExpired,
    VerificationCodeInvalid,
    VerificationCodeLocked,
    VerificationDeliveryUnavailable,
)
from accounts_buyers.models import BuyerAccount, VerificationCode
from accounts_buyers.serializers import (
    BuyerLoginSerializer,
    BuyerRegisterSerializer,
    VerificationCodeRequestSerializer,
)
from accounts_buyers.services import (
    clear_rate_limit,
    consume_verification_code,
    create_buyer_session,
    delete_buyer_session_cookie,
    deliver_verification_code,
    increment_rate_limit,
    issue_verification_code,
    rate_limit_key,
    rate_limit_reached,
    revoke_buyer_session,
    set_buyer_session_cookie,
)
from merchants.models import MerchantApplication

DUMMY_PASSWORD_HASH = make_password(None)


def _client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


def _merchant_application_brief(account: BuyerAccount) -> dict:
    """需求 12.2：申请店铺状态随买家 session 一次带回（头部不再单独发请求）。

    只取状态与店铺 public_id 两个轻字段；无申请时两者均为 None。
    """

    application = (
        MerchantApplication.objects.select_related("merchant")
        .only("status", "merchant__public_id")
        .filter(buyer=account)
        .first()
    )
    return {
        "merchant_application_status": application.status if application else None,
        "merchant_id": (
            str(application.merchant.public_id)
            if application is not None and application.merchant is not None
            else None
        ),
    }


def _ensure_display_name(account: BuyerAccount) -> str:
    """需求 13.5-6: 未设置用户名时生成 `user+4位数字+4位小写字母`（真站格式
    实证 user4323txlb），一次生成固定存库；已设置（含未来用户自改）则原样返回。"""

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


def _account_payload(account: BuyerAccount) -> dict:
    return {
        "id": str(account.public_id),
        "email": account.email,
        "phone": account.phone_e164,
        "status": account.status,
        # 需求 13.5-6: 头像下拉展示名（未设置时首次生成并固定存库）。
        "display_name": _ensure_display_name(account),
        # 迭代02：登录渠道（EMAIL / FACEBOOK / GOOGLE）。
        "auth_provider": account.auth_provider or BuyerAccount.AuthProvider.EMAIL,
        # docs/12 6-6: storefront gates Buy now / Add to cart on this flag.
        "purchase_whitelisted": account.purchase_whitelisted,
        # 余额支付真扣，购物端结账页展示真实余额（与商家钱包是两套独立账户）。
        "balance": str(account.balance),
        # 需求 12.2：申请店铺状态 + 已开通店铺 id（无申请时均为 None）。
        **_merchant_application_brief(account),
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class BuyerCsrfAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class VerificationCodeView(BuyerCsrfAPIView):
    def post(self, request):
        serializer = VerificationCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        limit_key = rate_limit_key(
            "verification-send",
            data["target"],
            _client_ip(request) or "unknown",
        )
        count = increment_rate_limit(limit_key, settings.VERIFICATION_CODE_SEND_WINDOW_SECONDS)
        if count > settings.VERIFICATION_CODE_SEND_LIMIT:
            raise BuyerApiError(
                business_code="VERIFICATION_CODE_RATE_LIMITED",
                message="Too many verification codes were requested. Try again later.",
                status_code=429,
            )

        code, record = issue_verification_code(**data)
        try:
            deliver_verification_code(channel=data["channel"], target=data["target"], code=code)
        except VerificationDeliveryUnavailable as exc:
            raise BuyerApiError(
                business_code="VERIFICATION_DELIVERY_UNAVAILABLE",
                message="This verification channel is not configured.",
                status_code=503,
            ) from exc

        payload = {
            "status": "accepted",
            "expires_at": record.expires_at.isoformat(),
        }
        if settings.VERIFICATION_CODE_TEST_MODE:
            payload["test_code"] = code
        return Response(payload, status=202)


class BuyerRegisterView(BuyerCsrfAPIView):
    def post(self, request):
        serializer = BuyerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        identifier_field = (
            "email" if data["channel"] == VerificationCode.Channel.EMAIL else "phone_e164"
        )

        if BuyerAccount.objects.filter(**{identifier_field: data["target"]}).exists():
            raise BuyerApiError(
                business_code="BUYER_ACCOUNT_EXISTS",
                message="An account already exists for this identifier.",
                status_code=409,
            )

        try:
            consume_verification_code(
                channel=data["channel"],
                target=data["target"],
                purpose=data["purpose"],
                code=data["verification_code"],
            )
            with transaction.atomic():
                now = timezone.now()
                account = BuyerAccount(**{identifier_field: data["target"]}, last_login_at=now)
                account.set_password(data["password"])
                if identifier_field == "email":
                    account.email_verified_at = now
                else:
                    account.phone_verified_at = now
                account.save()
        except VerificationCodeExpired as exc:
            raise BuyerApiError(
                business_code="VERIFICATION_CODE_EXPIRED",
                message="The verification code has expired.",
                status_code=400,
            ) from exc
        except VerificationCodeLocked as exc:
            raise BuyerApiError(
                business_code="VERIFICATION_CODE_LOCKED",
                message="Too many incorrect verification attempts.",
                status_code=429,
            ) from exc
        except VerificationCodeInvalid as exc:
            raise BuyerApiError(
                business_code="VERIFICATION_CODE_INVALID",
                message="The verification code is invalid.",
                status_code=400,
            ) from exc
        except IntegrityError as exc:
            raise BuyerApiError(
                business_code="BUYER_ACCOUNT_EXISTS",
                message="An account already exists for this identifier.",
                status_code=409,
            ) from exc

        token, _ = create_buyer_session(
            account=account,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        response = Response({"account": _account_payload(account)}, status=201)
        set_buyer_session_cookie(response, token)
        return response


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class BuyerEmailRegisterView(BuyerCsrfAPIView):
    """邮箱手动注册（迭代02 拍板）：自填账号 + 密码即可注册成功，不做邮箱验证码。

    账号（邮箱）唯一，系统 ID 始终唯一，以 ID 区分用户；登录渠道记录为 EMAIL。
    """

    def post(self, request):
        import re

        from django.db import IntegrityError
        from rest_framework.response import Response

        from accounts_buyers.services import create_buyer_session, set_buyer_session_cookie

        payload = request.data or {}
        email = str(payload.get("email") or "").strip().lower()
        password = str(payload.get("password") or "")
        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise BuyerApiError(
                business_code="EMAIL_INVALID", message="请输入有效的邮箱地址。", status_code=400
            )
        if len(password) < 8:
            raise BuyerApiError(
                business_code="PASSWORD_TOO_SHORT", message="密码至少 8 位。", status_code=400
            )
        if BuyerAccount.objects.filter(email=email).exists():
            raise BuyerApiError(
                business_code="BUYER_ACCOUNT_EXISTS",
                message="该邮箱已注册，请直接登录。",
                status_code=409,
            )
        try:
            with transaction.atomic():
                now = timezone.now()
                account = BuyerAccount(
                    email=email,
                    last_login_at=now,
                    auth_provider=BuyerAccount.AuthProvider.EMAIL,
                    email_verified_at=now,
                )
                account.set_password(password)
                account.save()
        except IntegrityError as exc:
            raise BuyerApiError(
                business_code="BUYER_ACCOUNT_EXISTS",
                message="该邮箱已注册，请直接登录。",
                status_code=409,
            ) from exc

        token, _ = create_buyer_session(
            account=account,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        response = Response({"account": _account_payload(account)}, status=201)
        set_buyer_session_cookie(response, token)
        return response


class BuyerLoginView(BuyerCsrfAPIView):
    def post(self, request):
        serializer = BuyerLoginSerializer(data=request.data, context={})
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        password = serializer.validated_data["password"]
        identifier_field = serializer.context["identifier_field"]
        limit_key = rate_limit_key(
            "login-failure",
            identifier,
            _client_ip(request) or "unknown",
        )

        if rate_limit_reached(limit_key, settings.BUYER_LOGIN_FAILURE_LIMIT):
            raise BuyerApiError(
                business_code="BUYER_LOGIN_RATE_LIMITED",
                message="Too many failed login attempts. Try again later.",
                status_code=429,
            )

        account = BuyerAccount.objects.filter(**{identifier_field: identifier}).first()
        password_valid = (
            account.check_password(password)
            if account
            else check_password(password, DUMMY_PASSWORD_HASH)
        )
        if not account or not password_valid:
            increment_rate_limit(limit_key, settings.BUYER_LOGIN_FAILURE_WINDOW_SECONDS)
            raise BuyerApiError(
                business_code="INVALID_CREDENTIALS",
                message="The identifier or password is incorrect.",
                status_code=401,
            )
        if not account.is_active:
            raise BuyerApiError(
                business_code="BUYER_ACCOUNT_DISABLED",
                message="This account is disabled.",
                status_code=403,
            )

        clear_rate_limit(limit_key)
        account.last_login_at = timezone.now()
        account.save(update_fields=["last_login_at", "updated_at"])
        token, _ = create_buyer_session(
            account=account,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        response = Response({"account": _account_payload(account)})
        set_buyer_session_cookie(response, token)
        return response


class BuyerLogoutView(BuyerCsrfAPIView):
    def post(self, request):
        revoke_buyer_session(getattr(request, "buyer_session", None))
        response = Response(status=204)
        delete_buyer_session_cookie(response)
        return response


class BuyerSessionView(BuyerCsrfAPIView):
    def get(self, request):
        account = getattr(request, "buyer_account", None)
        return Response(
            {
                "authenticated": account is not None,
                "account": _account_payload(account) if account else None,
                "csrf_token": get_token(request),
            }
        )
