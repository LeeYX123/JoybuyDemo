from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.models import (
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
    StaffTotpDevice,
)
from accounts_staff.permissions import StaffRbacPermission
from accounts_staff.serializers import StaffLoginSerializer, StaffRoleUpdateSerializer
from accounts_staff.services import (
    clear_rate_limit,
    create_staff_session,
    delete_staff_session_cookie,
    get_staff_permission_codes,
    increment_rate_limit,
    rate_limit_key,
    rate_limit_reached,
    revoke_staff_session,
    set_staff_session_cookie,
)
from audit.services import record_audit

DUMMY_PASSWORD_HASH = make_password(None)


def _client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


def _staff_payload(staff: StaffAccount) -> dict:
    role_codes = list(staff.roles.order_by("code").values_list("code", flat=True))
    permissions = sorted(get_staff_permission_codes(staff))
    totp_enrolled = StaffTotpDevice.objects.filter(
        staff=staff,
        disabled_at__isnull=True,
    ).exists()
    return {
        "id": str(staff.public_id),
        "email": staff.email,
        "display_name": staff.display_name,
        "status": staff.status,
        "roles": role_codes,
        "permissions": permissions,
        "totp_required": staff.requires_totp,
        "totp_enrolled": totp_enrolled,
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class StaffCsrfAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class StaffLoginView(StaffCsrfAPIView):
    def post(self, request):
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        limit_key = rate_limit_key(data["email"], _client_ip(request) or "unknown")

        if rate_limit_reached(limit_key):
            raise StaffApiError(
                business_code="STAFF_LOGIN_RATE_LIMITED",
                message="Too many failed login attempts. Try again later.",
                status_code=429,
            )

        staff = StaffAccount.objects.filter(email=data["email"]).first()
        password_valid = (
            staff.check_password(data["password"])
            if staff
            else check_password(data["password"], DUMMY_PASSWORD_HASH)
        )
        if not staff or not password_valid:
            increment_rate_limit(limit_key)
            raise StaffApiError(
                business_code="INVALID_STAFF_CREDENTIALS",
                message="The email or password is incorrect.",
                status_code=401,
            )
        if not staff.is_active:
            raise StaffApiError(
                business_code="STAFF_ACCOUNT_DISABLED",
                message="This staff account is disabled.",
                status_code=403,
            )

        # 登录只校验邮箱+密码；历史 TOTP 设备记录保留但不再参与登录。
        # 会话标记为已验证，保证下游 RBAC 链一致。
        clear_rate_limit(limit_key)
        staff.last_login_at = timezone.now()
        staff.save(update_fields=["last_login_at", "updated_at"])
        token, _ = create_staff_session(
            staff=staff,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
            totp_verified=True,
        )
        response = Response({"staff": _staff_payload(staff)})
        set_staff_session_cookie(response, token)
        return response


class StaffLogoutView(StaffCsrfAPIView):
    def post(self, request):
        revoke_staff_session(getattr(request, "staff_session", None))
        response = Response(status=204)
        delete_staff_session_cookie(response)
        return response


class StaffSessionView(StaffCsrfAPIView):
    def get(self, request):
        staff = getattr(request, "staff_account", None)
        return Response(
            {
                "authenticated": staff is not None,
                "staff": _staff_payload(staff) if staff else None,
                "csrf_token": get_token(request),
            }
        )


class StaffMeView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]

    def get(self, request):
        return Response({"staff": _staff_payload(request.staff_account)})


class StaffRoleAssignmentView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["staff.roles.manage"]

    def put(self, request, public_id):
        serializer = StaffRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            target = StaffAccount.objects.select_for_update().filter(public_id=public_id).first()
            if target is None:
                raise StaffApiError(
                    business_code="STAFF_ACCOUNT_NOT_FOUND",
                    message="The staff account was not found.",
                    status_code=404,
                )

            roles = list(PlatformRole.objects.filter(code__in=data["role_codes"]))
            found_codes = {role.code for role in roles}
            missing_codes = sorted(set(data["role_codes"]) - found_codes)
            if missing_codes:
                raise StaffApiError(
                    business_code="PLATFORM_ROLE_NOT_FOUND",
                    message=f"Unknown platform roles: {', '.join(missing_codes)}.",
                    status_code=400,
                )

            before_codes = list(target.roles.order_by("code").values_list("code", flat=True))
            StaffRoleAssignment.objects.filter(staff=target).delete()
            StaffRoleAssignment.objects.bulk_create(
                [
                    StaffRoleAssignment(
                        staff=target,
                        role=role,
                        assigned_by=request.staff_account,
                    )
                    for role in roles
                ]
            )
            after_codes = sorted(found_codes)
            record_audit(
                request=request,
                actor=request.staff_account,
                action="staff.roles.updated",
                target_type="staff_account",
                target_id=str(target.public_id),
                reason=data["reason"],
                before_state={"roles": before_codes},
                after_state={"roles": after_codes},
            )

        return Response({"staff": _staff_payload(target)})
