"""A16 账号与权限：管理员凭证 + 逐模块查看/操作。

模块目录见 ``accounts_staff.modules``；``manage`` 权限隐式包含 ``view``，
因此只读账号只授予 ``*.view``，菜单仍可见但写接口会 403。
"""

import re

from django.db import transaction
from django.db.models import Q
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.modules import MODULES, ROLE_TEMPLATES, module_catalog
from accounts_staff.permissions import StaffRbacPermission
from accounts_staff.services import get_staff_permission_codes
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, paginate, require

ACCOUNT_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")


def _staff_payload(staff: StaffAccount) -> dict:
    codes = get_staff_permission_codes(staff)
    modules = {}
    for module in MODULES:
        modules[module.code] = {
            "read": module.view in codes or module.manage in codes,
            "write": module.manage in codes,
        }
    return {
        "id": str(staff.public_id),
        "account": staff.email,
        "name": staff.display_name,
        "status": staff.status,
        "roles": list(staff.roles.order_by("code").values_list("code", flat=True)),
        "permissions": sorted(codes),
        "modules": modules,
        "is_protected": staff.roles.filter(is_platform_admin=True).exists(),
        "last_login_at": iso(staff.last_login_at),
        "created_at": iso(staff.created_at),
    }


def _resolve_module_codes(payload) -> tuple[set[str], set[str]]:
    """把前端提交的 modules 映射成权限码；写权限强制包含读权限。"""

    raw = payload.get("modules")
    if raw is None:
        return set(), set()
    if not isinstance(raw, dict):
        raise StaffApiError(
            business_code="MODULES_INVALID", message="模块权限格式不正确。", status_code=400
        )
    views: set[str] = set()
    manages: set[str] = set()
    for code, entry in raw.items():
        module = next((item for item in MODULES if item.code == code), None)
        if module is None:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("write"):
            manages.add(module.manage)
            views.add(module.view)
        elif entry.get("read"):
            views.add(module.view)
    return views, manages


def _apply_permissions(staff: StaffAccount, view_codes: set[str], manage_codes: set[str]):
    """把逐模块勾选落成角色：一个账号一个内置角色，权限取并集。"""

    role_code = f"staff-{str(staff.public_id)[:12]}"
    role, _ = PlatformRole.objects.get_or_create(
        code=role_code,
        defaults={
            "name": f"账号权限 · {staff.display_name}",
            "description": "由「账号与权限」按模块勾选自动维护。",
            "is_system": False,
        },
    )
    wanted = PlatformPermission.objects.filter(code__in=list(view_codes | manage_codes))
    role.permissions.set(wanted)
    StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)


class AdminStaffAccountsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["staff.roles.manage"]
    view_permissions = ["staff.roles.view"]

    def get(self, request):
        queryset = StaffAccount.objects.all().order_by("created_at", "pk")
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(email__icontains=query) | Q(display_name__icontains=query))
        rows, meta = paginate(queryset, request)
        return Response({"items": [_staff_payload(row) for row in rows], **meta})

    def post(self, request):
        payload = request.data or {}
        account = require(payload, "account", label="登录账号").strip().lower()
        if not ACCOUNT_PATTERN.match(account):
            raise StaffApiError(
                business_code="ACCOUNT_INVALID",
                message="账号需 3–64 位，仅允许字母、数字与 _ . @ - 。",
                status_code=400,
            )
        if StaffAccount.objects.filter(email=account).exists():
            raise StaffApiError(
                business_code="ACCOUNT_EXISTS", message="该账号已存在。", status_code=409
            )
        password = str(payload.get("password") or "")
        if len(password) < 8 or len(password) > 64:
            raise StaffApiError(
                business_code="PASSWORD_INVALID", message="密码需 8–64 位。", status_code=400
            )
        view_codes, manage_codes = _resolve_module_codes(payload)
        if not view_codes:
            raise StaffApiError(
                business_code="NO_MODULE",
                message="请至少授予一个可查看模块。",
                status_code=400,
            )

        with transaction.atomic():
            staff = StaffAccount(
                email=account,
                display_name=(payload.get("name") or account).strip()[:120],
                status=StaffAccount.Status.ACTIVE,
            )
            staff.set_password(password)
            staff.save()
            _apply_permissions(staff, view_codes, manage_codes)

        record_audit(
            request=request,
            actor=request.staff_account,
            action="STAFF_ACCOUNT_CREATED",
            target_type="staff_account",
            target_id=str(staff.public_id),
            reason="",
            before_state={},
            after_state={"account": account, "modules": sorted(view_codes | manage_codes)},
        )
        return Response({"staff": _staff_payload(staff)}, status=201)


class AdminStaffAccountDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["staff.roles.manage"]
    view_permissions = ["staff.roles.view"]

    def _get(self, public_id):
        staff = StaffAccount.objects.filter(public_id=public_id).first()
        if staff is None:
            raise StaffApiError(
                business_code="STAFF_NOT_FOUND", message="账号不存在。", status_code=404
            )
        return staff

    def get(self, request, public_id):
        return Response({"staff": _staff_payload(self._get(public_id))})

    def patch(self, request, public_id):
        staff = self._get(public_id)
        payload = request.data or {}
        protected = staff.roles.filter(is_platform_admin=True).exists()
        before = _staff_payload(staff)

        if payload.get("name"):
            staff.display_name = str(payload["name"]).strip()[:120]
        if payload.get("password"):
            password = str(payload["password"])
            if len(password) < 8 or len(password) > 64:
                raise StaffApiError(
                    business_code="PASSWORD_INVALID",
                    message="密码需 8–64 位。",
                    status_code=400,
                )
            staff.set_password(password)
        if payload.get("status"):
            status = str(payload["status"]).upper()
            if status not in dict(StaffAccount.Status.choices):
                raise StaffApiError(
                    business_code="STATUS_INVALID", message="账号状态无效。", status_code=400
                )
            if protected and status == StaffAccount.Status.DISABLED:
                raise StaffApiError(
                    business_code="PROTECTED_ACCOUNT",
                    message="超级管理员账号不能停用，避免自锁。",
                    status_code=400,
                )
            staff.status = status
        staff.save()

        if "modules" in payload:
            if protected:
                raise StaffApiError(
                    business_code="PROTECTED_ACCOUNT",
                    message="超级管理员权限不可移除。",
                    status_code=400,
                )
            view_codes, manage_codes = _resolve_module_codes(payload)
            if not view_codes:
                raise StaffApiError(
                    business_code="NO_MODULE",
                    message="请至少授予一个可查看模块。",
                    status_code=400,
                )
            _apply_permissions(staff, view_codes, manage_codes)

        record_audit(
            request=request,
            actor=request.staff_account,
            action="STAFF_ACCOUNT_UPDATED",
            target_type="staff_account",
            target_id=str(staff.public_id),
            reason="",
            before_state={k: before[k] for k in ("account", "status", "permissions")},
            after_state={
                "account": staff.email,
                "status": staff.status,
                "permissions": _staff_payload(staff)["permissions"],
            },
        )
        return Response({"staff": _staff_payload(staff)})


class AdminPermissionCatalogView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["staff.roles.manage"]
    view_permissions = ["staff.roles.view"]

    def get(self, request):
        return Response(
            {
                "modules": module_catalog(),
                "role_templates": [
                    {"code": code, "modules": modules} for code, modules in ROLE_TEMPLATES.items()
                ],
                "roles": [
                    {
                        "code": role.code,
                        "name": role.name,
                        "is_admin": role.is_platform_admin,
                        "permissions": sorted(role.permissions.values_list("code", flat=True)),
                    }
                    for role in PlatformRole.objects.order_by("code")
                ],
            }
        )
