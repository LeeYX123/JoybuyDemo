"""A10 商城首页轮播图。"""

from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from content.models import HomeBanner
from merchant_ops.api_utils import OpsAPIView, iso, paginate


def _payload(banner: HomeBanner) -> dict:
    return {
        "id": str(banner.public_id),
        "title": banner.title,
        "description": banner.description,
        "image": banner.image_url,
        "href": banner.href,
        "sort": banner.sort_order,
        "enabled": banner.enabled,
        "updated_at": iso(banner.updated_at),
    }


def _validated(payload: dict, *, partial: bool = False) -> dict:
    values = {}
    if not partial or "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            raise StaffApiError(
                business_code="TITLE_REQUIRED", message="轮播图标题不能为空。", status_code=400
            )
        if len(title) > 40:
            raise StaffApiError(
                business_code="TITLE_TOO_LONG",
                message="标题最多 40 个字。",
                status_code=400,
            )
        values["title"] = title
    if not partial or "description" in payload:
        description = (payload.get("description") or "").strip()
        if len(description) > 100:
            raise StaffApiError(
                business_code="DESCRIPTION_TOO_LONG",
                message="小字描述最多 100 个字。",
                status_code=400,
            )
        values["description"] = description
    if not partial or "image" in payload:
        image = (payload.get("image") or "").strip()
        if not image:
            raise StaffApiError(
                business_code="IMAGE_REQUIRED",
                message="请上传轮播图片或填写 https 图片链接。",
                status_code=400,
            )
        values["image_url"] = image
    if "href" in payload:
        values["href"] = (payload.get("href") or "").strip()
    if "sort" in payload:
        try:
            sort = int(payload.get("sort") or 0)
        except (TypeError, ValueError):
            raise StaffApiError(
                business_code="SORT_INVALID", message="排序必须是非负整数。", status_code=400
            ) from None
        if sort < 0:
            raise StaffApiError(
                business_code="SORT_INVALID", message="排序必须是非负整数。", status_code=400
            )
        values["sort_order"] = sort
    if "enabled" in payload:
        values["enabled"] = bool(payload.get("enabled"))
    return values


class AdminBannersView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.banners.manage"]
    view_permissions = ["cms.banners.view"]

    def get(self, request):
        queryset = HomeBanner.objects.all()
        enabled = (request.query_params.get("enabled") or "").strip()
        if enabled in {"1", "true"}:
            queryset = queryset.filter(enabled=True)
        elif enabled in {"0", "false"}:
            queryset = queryset.filter(enabled=False)
        rows, meta = paginate(queryset, request)
        return Response({"items": [_payload(row) for row in rows], **meta})

    def post(self, request):
        values = _validated(request.data or {})
        banner = HomeBanner.objects.create(**values)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="BANNER_CREATED",
            target_type="home_banner",
            target_id=str(banner.public_id),
            reason="",
            before_state={},
            after_state={"title": banner.title, "sort": banner.sort_order},
        )
        return Response({"banner": _payload(banner)}, status=201)


class AdminBannerDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.banners.manage"]
    view_permissions = ["cms.banners.view"]

    def _get(self, public_id):
        banner = HomeBanner.objects.filter(public_id=public_id).first()
        if banner is None:
            raise StaffApiError(
                business_code="BANNER_NOT_FOUND", message="轮播图不存在。", status_code=404
            )
        return banner

    def get(self, request, public_id):
        return Response({"banner": _payload(self._get(public_id))})

    def patch(self, request, public_id):
        banner = self._get(public_id)
        before = _payload(banner)
        values = _validated(request.data or {}, partial=True)
        for field, value in values.items():
            setattr(banner, field, value)
        banner.save()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="BANNER_UPDATED",
            target_type="home_banner",
            target_id=str(banner.public_id),
            reason="",
            before_state=before,
            after_state=_payload(banner),
        )
        return Response({"banner": _payload(banner)})

    def delete(self, request, public_id):
        banner = self._get(public_id)
        snapshot = _payload(banner)
        banner.delete()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="BANNER_DELETED",
            target_type="home_banner",
            target_id=str(public_id),
            reason="",
            before_state=snapshot,
            after_state={},
        )
        return Response(status=204)


class AdminBannerActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.banners.manage"]

    def post(self, request, public_id):
        banner = HomeBanner.objects.filter(public_id=public_id).first()
        if banner is None:
            raise StaffApiError(
                business_code="BANNER_NOT_FOUND", message="轮播图不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        before = {"enabled": banner.enabled}
        if action == "enable":
            banner.enabled = True
        elif action == "disable":
            banner.enabled = False
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        banner.save(update_fields=["enabled", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"BANNER_{action.upper()}",
            target_type="home_banner",
            target_id=str(banner.public_id),
            reason="",
            before_state=before,
            after_state={"enabled": banner.enabled},
        )
        return Response({"banner": _payload(banner)})
