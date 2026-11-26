import logging
import urllib.parse

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts_buyers import oauth
from accounts_buyers.api_exceptions import BuyerApiError
from accounts_buyers.domain import (
    VerificationCodeExpired,
    VerificationCodeInvalid,
    VerificationCodeLocked,
    VerificationDeliveryUnavailable,
)
from accounts_buyers.models import BuyerAccount, VerificationCode
from accounts_buyers.normalization import normalize_identifier
from accounts_buyers.serializers import (
    BuyerLoginSerializer,
    BuyerRegisterSerializer,
    VerificationCodeRequestSerializer,
)
from accounts_buyers.services import (
    clear_rate_limit,
    consume_merchant_handoff_token,
    consume_verification_code,
    create_buyer_session,
    delete_buyer_session_cookie,
    deliver_verification_code,
    ensure_display_name,
    increment_rate_limit,
    issue_verification_code,
    rate_limit_key,
    rate_limit_reached,
    revoke_buyer_session,
    set_buyer_session_cookie,
)
from merchants.models import MerchantApplication

logger = logging.getLogger(__name__)

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
    """兼容旧调用点：生成规则已移到 `services.ensure_display_name`（oauth 也用它）。"""

    return ensure_display_name(account)


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
                account = BuyerAccount(
                    **{identifier_field: data["target"]},
                    last_login_at=now,
                    # 批次 CA：新注册买家默认不进购买白名单（后台可手动加入）。
                    purchase_whitelisted=False,
                )
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
                    # 批次 CA：新注册买家默认不进购买白名单（后台可手动加入）。
                    purchase_whitelisted=False,
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


class BuyerMerchantHandoffView(BuyerCsrfAPIView):
    """POST /api/v1/auth/buyer/merchant-handoff：兑换商家端一次性 token。

    无需登录（这是登录入口）。与其它买家写接口一致走 ``BuyerCsrfAPIView``：
    storefront 先 GET /auth/buyer/session 拿 csrftoken，再带 X-CSRFToken POST。
    兑换成功后在**购物端自己的 host** 上写 host-only session cookie。
    """

    def post(self, request):
        token = str((request.data or {}).get("token") or "").strip()
        account = consume_merchant_handoff_token(token)
        if account is None:
            raise BuyerApiError(
                business_code="HANDOFF_TOKEN_INVALID",
                message="登录凭证已过期，请从商家端重新进入",
                status_code=400,
            )

        session_token, _session = create_buyer_session(
            account=account,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        response = Response({"email": account.email})
        set_buyer_session_cookie(response, session_token)
        return response


# ---------------------------------------------------------------------------
# 三方登录（docs/16）：三个端点都是 GET，安全性靠 state + PKCE
# ---------------------------------------------------------------------------


def _oauth_error_redirect(code: str) -> HttpResponseRedirect:
    """失败统一回商城登录页（同域），由前端按 oauth_error 渲染文案。"""

    query = urllib.parse.urlencode({"oauth_error": code})
    return HttpResponseRedirect(f"{settings.STOREFRONT_BASE_URL}/auth/login?{query}")


class OAuthProvidersView(BuyerCsrfAPIView):
    """GET /api/v1/auth/buyer/oauth/providers：全部支持渠道 + enabled 标记。

    未配置凭据的渠道也返回（enabled=False），前端据此渲染同款按钮但点击提示不可用。
    """

    def get(self, request):
        return Response({"providers": oauth.providers_payload()})


class BuyerIdentifierLookupView(BuyerCsrfAPIView):
    """POST /api/v1/auth/buyer/identifier/lookup：email-first 第一步的分流判断。

    只回答「这个邮箱/手机号是否已注册」，**不返回**账号 id、登录渠道、注册时间等任何
    可关联信息。该接口天然可被用于账号枚举（docs/17 §4 / §7），因此：
    - 限额比登录更紧（默认 5 次/60s/IP+标识指纹），且命中与未命中**都计数**；
    - 无论命中与否都跑一次 dummy 哈希校验，避免靠响应耗时侧信道区分。
    """

    def post(self, request):
        raw = str((request.data or {}).get("identifier") or "").strip()
        try:
            field, value = normalize_identifier(raw)
        except ValidationError as exc:
            raise BuyerApiError(
                business_code="IDENTIFIER_INVALID",
                message="请输入有效的邮箱或手机号。",
                status_code=400,
            ) from exc

        limit_key = rate_limit_key(
            "identifier-lookup", value, _client_ip(request) or "unknown"
        )
        if (
            increment_rate_limit(limit_key, settings.IDENTIFIER_LOOKUP_WINDOW_SECONDS)
            > settings.IDENTIFIER_LOOKUP_LIMIT
        ):
            raise BuyerApiError(
                business_code="IDENTIFIER_LOOKUP_RATE_LIMITED",
                message="查询过于频繁，请稍后再试。",
                status_code=429,
            )

        # 禁用账号也按「存在」返回：让用户走正常的密码步，由登录接口报禁用，
        # 避免多一个"存在但被禁用"的可枚举状态。
        exists = BuyerAccount.objects.filter(**{field: value}).exists()
        check_password(value, DUMMY_PASSWORD_HASH)  # 恒定耗时
        return Response({"kind": "EMAIL" if field == "email" else "PHONE", "exists": exists})


class OAuthStartView(BuyerCsrfAPIView):
    """GET .../oauth/<provider>/start?next=/account → 302 到授权页。"""

    def get(self, request, provider):
        limit_key = rate_limit_key(
            "oauth-start", provider, _client_ip(request) or "unknown"
        )
        if (
            increment_rate_limit(limit_key, settings.OAUTH_START_WINDOW_SECONDS)
            > settings.OAUTH_START_LIMIT
        ):
            return _oauth_error_redirect("rate_limited")
        try:
            return HttpResponseRedirect(oauth.start_login(provider, request.GET.get("next")))
        except oauth.OAuthError as exc:
            return _oauth_error_redirect(exc.code)


class OAuthCallbackView(BuyerCsrfAPIView):
    """GET .../oauth/<provider>/callback?code&state：换 token、认人、种 session cookie。

    回调落在商城同域（生产 nginx `/api/` → Django；开发走 Nuxt `/api` 代理），
    所以这里种下的 host-only cookie 浏览器能直接带到商城页面。
    """

    def get(self, request, provider):
        try:
            account, next_path = oauth.complete_login(
                provider, code=request.GET.get("code"), state=request.GET.get("state")
            )
        except oauth.OAuthError as exc:
            # 只记业务码，不记 provider 原文（可能带 code / token）。
            logger.info("buyer_oauth_failed provider=%s code=%s", provider, exc.code)
            return _oauth_error_redirect(exc.code)

        session_token, _session = create_buyer_session(
            account=account,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        logger.info(
            "buyer_oauth_login provider=%s account=%s", provider, account.public_id
        )
        response = HttpResponseRedirect(f"{settings.STOREFRONT_BASE_URL}{next_path}")
        set_buyer_session_cookie(response, session_token)
        return response
