"""平台管理后台：频道页 banner（``/minihome/<code>`` 顶部轮播图）配置。

与首页轮播图 / 首页活动卡片同一套逐模块口径：权限码
``cms.channel_banners.manage``（编辑）与 ``cms.channel_banners.view``（查看），
写操作写审计日志。频道维度用 ``channel_code`` 过滤，图片只接受本地
``/media/`` 路径。
"""

from django.db import transaction
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from content.channel_banner_services import (
    ChannelBannerError,
    channel_options,
    create_banner,
    move_banner,
    serialize_banner,
    update_banner,
)
from content.models import ChannelBanner
from merchant_ops.api_utils import OpsAPIView


def _error(exc: ChannelBannerError) -> StaffApiError:
    return StaffApiError(business_code=exc.code, message=exc.message, status_code=exc.status_code)


def _find(public_id) -> ChannelBanner:
    banner = ChannelBanner.objects.filter(public_id=public_id).first()
    if banner is None:
        raise StaffApiError(
            business_code="BANNER_NOT_FOUND", message="频道 banner 不存在。", status_code=404
        )
    return banner


class AdminChannelBannersView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_banners.manage"]
    view_permissions = ["cms.channel_banners.view"]

    def get(self, request):
        channel_code = str(request.query_params.get("channel_code") or "").strip()
        rows = ChannelBanner.objects.all()
        if channel_code:
            rows = rows.filter(channel_code=channel_code)
        rows = rows.order_by("channel_code", "sort_order", "public_id")
        items = [serialize_banner(row) for row in rows]
        return Response({"channel_code": channel_code, "items": items, "total": len(items)})

    def post(self, request):
        try:
            with transaction.atomic():
                banner = create_banner(payload=request.data or {})
        except ChannelBannerError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_BANNER_CREATED",
            target_type="channel_banner",
            target_id=str(banner.public_id),
            reason="",
            before_state={},
            after_state={
                "channel_code": banner.channel_code,
                "image_url": banner.image_url,
                "href": banner.href,
            },
        )
        return Response({"banner": serialize_banner(banner)}, status=201)


class AdminChannelBannerChannelsView(OpsAPIView):
    """频道下拉：有 minihome code 的一级类目。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_banners.manage"]
    view_permissions = ["cms.channel_banners.view"]

    def get(self, request):
        items = channel_options()
        return Response({"items": items, "total": len(items)})


class AdminChannelBannerDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_banners.manage"]
    view_permissions = ["cms.channel_banners.view"]

    def get(self, request, public_id):
        return Response({"banner": serialize_banner(_find(public_id))})

    def patch(self, request, public_id):
        banner = _find(public_id)
        before = serialize_banner(banner)
        try:
            banner = update_banner(banner, payload=request.data or {})
        except ChannelBannerError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_BANNER_UPDATED",
            target_type="channel_banner",
            target_id=str(banner.public_id),
            reason="",
            before_state=before,
            after_state=serialize_banner(banner),
        )
        return Response({"banner": serialize_banner(banner)})

    def delete(self, request, public_id):
        banner = _find(public_id)
        snapshot = serialize_banner(banner)
        banner.delete()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_BANNER_DELETED",
            target_type="channel_banner",
            target_id=str(public_id),
            reason="",
            before_state=snapshot,
            after_state={},
        )
        return Response({"deleted": True}, status=200)


class AdminChannelBannerActionsView(OpsAPIView):
    """排序（上移/下移）与启用开关。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_banners.manage"]
    view_permissions = ["cms.channel_banners.view"]

    def post(self, request, public_id):
        banner = _find(public_id)
        payload = request.data or {}
        action = str(payload.get("action") or "").strip().lower()
        try:
            if action == "move":
                move_banner(banner, direction=payload.get("direction"))
            elif action == "toggle":
                banner.enabled = not banner.enabled
                banner.save(update_fields=["enabled", "updated_at"])
            else:
                raise StaffApiError(
                    business_code="ACTION_INVALID", message="不支持的操作。", status_code=400
                )
        except ChannelBannerError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_BANNER_ACTION",
            target_type="channel_banner",
            target_id=str(banner.public_id),
            reason="",
            before_state={},
            after_state={"action": action, "enabled": banner.enabled},
        )
        return Response({"banner": serialize_banner(banner)})
