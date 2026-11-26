"""平台管理后台：活动页/店铺页配置（2026-11-25）。

挂在【服务与运营】分组，权限码复用 ``cms.campaign.manage`` / ``cms.campaign.view``
（与首页活动卡片同一套逐模块口径，避免为一次性功能新增 RBAC 迁移）。

接口：
- ``GET/POST /api/v1/admin/activity-pages?kind=ACTIVE|STORE``  列表 / 新建
- ``GET/PATCH/DELETE /api/v1/admin/activity-pages/<public_id>``  详情 / 更新 / 删除
- ``POST /api/v1/admin/activity-pages/<public_id>/sections``  新增分区
- ``PATCH/DELETE /api/v1/admin/activity-pages/<public_id>/sections/<section_id>``
- ``PUT /api/v1/admin/activity-pages/<public_id>/sections/<section_id>/products``
"""

from django.db import transaction
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from content.activity_services import (
    ActivityPageError,
    create_page,
    create_section,
    replace_section_products,
    serialize_page,
    update_page,
    update_section,
)
from content.models import ActivityPage, ActivitySection
from merchant_ops.api_utils import OpsAPIView

KIND_ALIASES = {"active": ActivityPage.Kind.ACTIVITY, "store": ActivityPage.Kind.STORE}


def _error(exc: ActivityPageError) -> StaffApiError:
    return StaffApiError(
        business_code=exc.code, message=exc.message, status_code=exc.status_code
    )


def _resolve_kind(value: str, *, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        if default:
            return default
        raise StaffApiError(
            business_code="KIND_INVALID", message="页面类型不正确。", status_code=400
        )
    upper = text.upper()
    if upper in {choice.value for choice in ActivityPage.Kind}:
        return upper
    alias = KIND_ALIASES.get(text.lower())
    if alias:
        return alias
    raise StaffApiError(
        business_code="KIND_INVALID", message="页面类型不正确。", status_code=400
    )


def _page_or_404(public_id) -> ActivityPage:
    page = ActivityPage.objects.filter(public_id=public_id).first()
    if page is None:
        raise StaffApiError(
            business_code="PAGE_NOT_FOUND", message="活动页不存在。", status_code=404
        )
    return page


def _section_or_404(page: ActivityPage, section_public_id) -> ActivitySection:
    section = page.sections.filter(public_id=section_public_id).first()
    if section is None:
        raise StaffApiError(
            business_code="SECTION_NOT_FOUND", message="分区不存在。", status_code=404
        )
    return section


class AdminActivityPagesView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def get(self, request):
        kind = _resolve_kind(request.query_params.get("kind"), default=ActivityPage.Kind.ACTIVITY)
        rows = ActivityPage.objects.filter(kind=kind).order_by("sort_order", "pk")
        items = []
        for page in rows:
            data = serialize_page(page, include_products=False)
            data["section_count"] = page.sections.count()
            data["product_count"] = sum(
                section.items.count() for section in page.sections.all()
            )
            items.append(data)
        return Response({"kind": kind, "items": items, "total": len(items)})

    def post(self, request):
        payload = dict(request.data or {})
        payload.setdefault("kind", _resolve_kind(request.query_params.get("kind"), default=""))
        try:
            with transaction.atomic():
                page = create_page(payload)
        except ActivityPageError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_PAGE_CREATED",
            target_type="activity_page",
            target_id=str(page.public_id),
            reason="",
            before_state={},
            after_state={
                "kind": page.kind,
                "external_id": page.external_id,
                "title": page.title,
            },
        )
        return Response({"page": serialize_page(page)}, status=201)


class AdminActivityPageOptionsView(OpsAPIView):
    """活动页下拉选项（2026-11-26，ADR-0002）：给频道卡面板绑定落地页用。

    轻量列表：只给 id/kind/external_id/title/enabled，不走整页序列化。
    权限用卡片面板自己的码，避免运营为绑卡再申请活动页权限。
    """

    permission_classes = [StaffRbacPermission]
    view_permissions = ["cms.channel_page_cards.view"]

    def get(self, request):
        rows = ActivityPage.objects.order_by("kind", "external_id")
        items = [
            {
                "id": str(page.public_id),
                "kind": page.kind,
                "external_id": page.external_id,
                "title": page.title,
                "enabled": page.enabled,
            }
            for page in rows
        ]
        return Response({"items": items, "total": len(items)})


class AdminActivityPageDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def get(self, request, public_id):
        page = _page_or_404(public_id)
        return Response({"page": serialize_page(page)})

    def patch(self, request, public_id):
        page = _page_or_404(public_id)
        before = {"title": page.title, "enabled": page.enabled, "hero_image": page.hero_image}
        try:
            page = update_page(page, dict(request.data or {}))
        except ActivityPageError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_PAGE_UPDATED",
            target_type="activity_page",
            target_id=str(page.public_id),
            reason="",
            before_state=before,
            after_state={
                "title": page.title,
                "enabled": page.enabled,
                "hero_image": page.hero_image,
            },
        )
        return Response({"page": serialize_page(page)})

    def delete(self, request, public_id):
        page = _page_or_404(public_id)
        kind, external_id, title = page.kind, page.external_id, page.title
        page.delete()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_PAGE_DELETED",
            target_type="activity_page",
            target_id=str(public_id),
            reason="",
            before_state={"kind": kind, "external_id": external_id, "title": title},
            after_state={},
        )
        return Response({"deleted": True})


class AdminActivityPageSectionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def post(self, request, public_id):
        page = _page_or_404(public_id)
        try:
            section = create_section(page, dict(request.data or {}))
        except ActivityPageError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_SECTION_CREATED",
            target_type="activity_page",
            target_id=str(page.public_id),
            reason="",
            before_state={},
            after_state={
                "section": str(section.public_id),
                "kind": section.kind,
                "title": section.title,
            },
        )
        return Response({"page": serialize_page(page)}, status=201)


class AdminActivityPageSectionDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def patch(self, request, public_id, section_id):
        page = _page_or_404(public_id)
        section = _section_or_404(page, section_id)
        try:
            update_section(section, dict(request.data or {}))
        except ActivityPageError as exc:
            raise _error(exc) from exc
        return Response({"page": serialize_page(page)})

    def delete(self, request, public_id, section_id):
        page = _page_or_404(public_id)
        section = _section_or_404(page, section_id)
        section.delete()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_SECTION_DELETED",
            target_type="activity_page",
            target_id=str(page.public_id),
            reason="",
            before_state={"section": str(section_id)},
            after_state={},
        )
        return Response({"page": serialize_page(page)})


class AdminActivityPageSectionProductsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def put(self, request, public_id, section_id):
        page = _page_or_404(public_id)
        section = _section_or_404(page, section_id)
        if section.kind != ActivitySection.Kind.PRODUCTS:
            raise StaffApiError(
                business_code="SECTION_NOT_PRODUCTS",
                message="只有商品楼层可以选品。",
                status_code=400,
            )
        ids = (request.data or {}).get("products") or []
        try:
            count = replace_section_products(section, list(ids))
        except ActivityPageError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_SECTION_PRODUCTS_SET",
            target_type="activity_page",
            target_id=str(page.public_id),
            reason="",
            before_state={},
            after_state={"section": str(section.public_id), "products": count},
        )
        return Response({"page": serialize_page(page)})
