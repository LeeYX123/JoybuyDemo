from rest_framework.permissions import BasePermission

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.services import get_staff_permission_codes


class StaffRbacPermission(BasePermission):
    def has_permission(self, request, view):
        staff = getattr(request, "staff_account", None)
        if staff is None:
            raise StaffApiError(
                business_code="STAFF_AUTH_REQUIRED",
                message="Staff authentication is required.",
                status_code=401,
            )

        session = getattr(request, "staff_session", None)
        if staff.requires_totp and (session is None or session.totp_verified_at is None):
            raise StaffApiError(
                business_code="STAFF_TOTP_REQUIRED",
                message="TOTP verification is required for this staff account.",
                status_code=403,
            )

        resolver = getattr(view, "resolve_required_permissions", None)
        if callable(resolver):
            required = set(resolver(request))
        else:
            required = set(getattr(view, "required_permissions", []))
        if not required:
            return True

        granted = get_staff_permission_codes(staff)
        if not required.issubset(granted):
            raise StaffApiError(
                business_code="STAFF_PERMISSION_DENIED",
                message="The staff account does not have the required permission.",
                status_code=403,
            )
        return True
