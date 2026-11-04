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

DUMMY_PASSWORD_HASH = make_password(None)


def _client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


def _account_payload(account: BuyerAccount) -> dict:
    return {
        "id": str(account.public_id),
        "email": account.email,
        "phone": account.phone_e164,
        "status": account.status,
        # docs/12 6-6: storefront gates Buy now / Add to cart on this flag.
        "purchase_whitelisted": account.purchase_whitelisted,
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
