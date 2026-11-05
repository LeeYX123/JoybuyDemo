"""平台管理端 / 商家端共用的图片上传接口。

落盘与校验都在 ``media.uploads`` 里，这里只处理「谁能传哪种图」：
管理端按用途校验对应模块的写权限（A16 逐模块口径），商家端按店铺角色校验。
"""

from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from media.uploads import UploadError, store_upload
from merchant_ops.api_utils import OpsAPIView
from merchant_ops.merchant_context import MerchantAPIView, merchant_permission_codes

# 用途 → 管理端需要的权限码。传活动图和商品图是不同模块的事，不能互相顶替。
ADMIN_PURPOSE_PERMISSIONS = {
    "product": "catalog.pool.manage",
    "banner": "cms.banners.manage",
    "review": "notifications.manage",
    "activity": "activities.manage",
    "avatar": "merchants.manage",
}

# 商家端只开放这三类：商品图、店铺头像、售后凭证（凭证复用 review 桶）。
MERCHANT_PURPOSE_PERMISSIONS = {
    "product": "merchant.listings.manage",
    "avatar": "merchant.store.manage",
    "review": "merchant.aftersales.manage",
}


def _run_upload(request, *, tenant_type: str, tenant_id: str) -> Response:
    payload = request.data or {}
    purpose = str(payload.get("purpose") or "").strip().lower()
    file = request.FILES.get("file")
    if file is None:
        raise StaffApiError(
            business_code="FILE_REQUIRED", message="请选择要上传的图片。", status_code=400
        )
    try:
        result = store_upload(file, purpose=purpose)
    except UploadError as exc:
        raise StaffApiError(
            business_code=exc.code, message=exc.message, status_code=exc.status_code
        ) from exc

    record_audit(
        request=request,
        actor=request.staff_account,
        action="MEDIA_UPLOADED",
        target_type="media_asset",
        target_id=result["sha256"],
        reason="",
        before_state={},
        after_state={
            "purpose": purpose,
            "url": result["url"],
            "byte_size": result["byte_size"],
            "mime_type": result["mime_type"],
        },
        tenant_type=tenant_type,
        tenant_id=tenant_id,
    )
    return Response({"media": result}, status=201)


class AdminMediaUploadView(OpsAPIView):
    """管理端上传入口。"""

    permission_classes = [StaffRbacPermission]

    def resolve_required_permissions(self, request):
        purpose = str((request.data or {}).get("purpose") or "").strip().lower()
        code = ADMIN_PURPOSE_PERMISSIONS.get(purpose)
        # 用途非法时仍要求一个写权限，避免变成「无权限也能打通上传」的后门；
        # 真正的用途错误由 store_upload 抛出 UPLOAD_PURPOSE_INVALID。
        return [code or "catalog.pool.manage"]

    def post(self, request):
        return _run_upload(request, tenant_type="PLATFORM", tenant_id="")


class MerchantMediaUploadView(MerchantAPIView):
    """商家端上传入口（商品图 / 店铺头像 / 售后凭证）。"""

    def post(self, request):
        purpose = str((request.data or {}).get("purpose") or "").strip().lower()
        required = MERCHANT_PURPOSE_PERMISSIONS.get(purpose)
        # 先判用途合法性，再看角色权限，避免「用途写错」被误报成没权限。
        if required is None:
            raise StaffApiError(
                business_code="UPLOAD_PURPOSE_INVALID",
                message=f"上传用途不正确，可选：{'、'.join(sorted(MERCHANT_PURPOSE_PERMISSIONS))}。",
                status_code=400,
            )
        if required not in merchant_permission_codes(request.membership):
            raise StaffApiError(
                business_code="MERCHANT_PERMISSION_DENIED",
                message="当前店铺角色无权上传该类图片。",
                status_code=403,
            )
        return _run_upload(
            request,
            tenant_type="MERCHANT",
            tenant_id=str(request.merchant.public_id),
        )
