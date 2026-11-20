"""平台管理后台：频道页商品楼层（``/minihome/<code>``）配置接口。

批次 H（2026-11-19）：默认配置由 ``seed_channel_modules`` 落库，本接口供
后台改楼层标题/排序/开关与商品清单（商品本身由导入流程维护，这里不改）。
权限码 ``cms.channel_modules.manage`` / ``cms.channel_modules.view``。
"""

from django.db import transaction
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from content.channel_module_services import (
    ChannelModuleError,
    list_modules,
    serialize_admin_module,
    update_module,
)
from merchant_ops.api_utils import OpsAPIView


def _error(exc: ChannelModuleError) -> StaffApiError:
    return StaffApiError(business_code=exc.code, message=exc.message, status_code=exc.status_code)


class AdminChannelModulesView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_modules.manage"]
    view_permissions = ["cms.channel_modules.view"]

    def get(self, request):
        channel_code = str(request.query_params.get("channel_code") or "").strip()
        items = [serialize_admin_module(row) for row in list_modules(channel_code)]
        return Response({"channel_code": channel_code, "items": items, "total": len(items)})


class AdminChannelModuleDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_modules.manage"]
    view_permissions = ["cms.channel_modules.view"]

    def get(self, request, public_id):
        rows = [row for row in list_modules() if str(row.public_id) == str(public_id)]
        if not rows:
            raise StaffApiError(
                business_code="MODULE_NOT_FOUND", message="频道楼层不存在。", status_code=404
            )
        return Response({"module": serialize_admin_module(rows[0])})

    def put(self, request, public_id):
        try:
            with transaction.atomic():
                module = update_module(public_id, request.data or {})
        except ChannelModuleError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_MODULE_UPDATED",
            target_type="channel_module",
            target_id=str(module.public_id),
            reason="",
            before_state={},
            after_state={
                "channel_code": module.channel_code,
                "title_en": module.title_en,
                "title_zh": module.title_zh,
                "sort_order": module.sort_order,
                "enabled": module.enabled,
                "products": module.items.count(),
            },
        )
        return Response({"module": serialize_admin_module(module)})
