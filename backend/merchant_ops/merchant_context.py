"""商家端（merchant-web）身份与上下文。

复用 ``staff_account`` 登录，不另建商家账号表：能进哪个店由
``merchant_membership`` 决定，能做什么由该 membership 角色的
``merchant_permission`` 决定。多店成员用 ``X-Merchant-Id`` 头显式指定，
不做隐式「取第一个」——否则切店会静默串店。
"""

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.views import StaffCsrfAPIView
from merchants.models import Merchant, MerchantMembership


class MerchantContextError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 403):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def memberships_for(staff):
    return (
        MerchantMembership.objects.select_related("merchant", "role")
        .filter(staff=staff, status=MerchantMembership.Status.ACTIVE)
        .order_by("merchant__created_at")
    )


def merchant_payload(merchant: Merchant, membership=None) -> dict:
    return {
        "id": str(merchant.public_id),
        "name": merchant.display_name,
        "avatar": merchant.avatar_url,
        "status": merchant.onboarding_status,
        "credit_score": str(merchant.credit_score),
        "deposit_enabled": merchant.deposit_enabled,
        "deposit_initial_paid": merchant.deposit_initial_paid,
        "can_operate": merchant.can_operate,
        "role": membership.role.name if membership else "",
    }


def resolve_merchant_context(request) -> tuple[Merchant, MerchantMembership]:
    """解析当前请求操作的店铺与成员关系。"""

    staff = getattr(request, "staff_account", None)
    if staff is None:
        raise MerchantContextError("MERCHANT_AUTH_REQUIRED", "请先登录商家账号。", status_code=401)
    memberships = list(memberships_for(staff))
    if not memberships:
        raise MerchantContextError(
            "MERCHANT_MEMBERSHIP_REQUIRED", "该账号未绑定任何店铺。", status_code=403
        )

    requested = (request.headers.get("X-Merchant-Id") or "").strip()
    if requested:
        for membership in memberships:
            if str(membership.merchant.public_id) == requested:
                return membership.merchant, membership
        raise MerchantContextError("MERCHANT_NOT_ACCESSIBLE", "无权访问该店铺。", status_code=403)

    if len(memberships) > 1:
        raise MerchantContextError(
            "MERCHANT_CONTEXT_REQUIRED",
            "该账号属于多家店铺，请先选择要操作的店铺。",
            status_code=400,
        )
    return memberships[0].merchant, memberships[0]


def merchant_permission_codes(membership: MerchantMembership) -> set[str]:
    return set(membership.role.permissions.values_list("code", flat=True))


class MerchantAPIView(StaffCsrfAPIView):
    """商家端接口基类：先过员工会话，再解析店铺上下文与权限。"""

    required_merchant_permissions: tuple[str, ...] = ()
    permission_any: tuple[str, ...] = ()
    # 少数接口（例如「可选店铺列表」）本身就是用来选店铺的，不能先要店铺上下文。
    skip_context = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.skip_context:
            return
        merchant, membership = resolve_merchant_context(request)
        request.merchant = merchant
        request.membership = membership

        codes = merchant_permission_codes(membership)
        needed = set(getattr(self, "required_merchant_permissions", ()) or ())
        if needed and not needed.issubset(codes):
            raise StaffApiError(
                business_code="MERCHANT_PERMISSION_DENIED",
                message="当前店铺角色无权执行该操作。",
                status_code=403,
            )
        any_of = set(getattr(self, "permission_any", ()) or ())
        if any_of and not (any_of & codes):
            raise StaffApiError(
                business_code="MERCHANT_PERMISSION_DENIED",
                message="当前店铺角色无权执行该操作。",
                status_code=403,
            )

    def handle_exception(self, exc):
        from accounts_buyers.services import BuyerWalletError
        from merchant_ops.services import MerchantOpsError
        from merchants.services import MerchantAdminError

        if isinstance(exc, MerchantContextError):
            exc = StaffApiError(
                business_code=exc.code, message=exc.message, status_code=exc.status_code
            )
        elif isinstance(exc, (MerchantOpsError, MerchantAdminError, BuyerWalletError)):
            # 复用域层错误码，别让商家端把 400 变成 500。
            exc = StaffApiError(
                business_code=exc.code, message=exc.message, status_code=exc.status_code
            )
        return super().handle_exception(exc)
