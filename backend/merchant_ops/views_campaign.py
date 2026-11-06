"""平台管理后台：首页活动卡片（搜索框下方 10 宫格）的设置入口。

挂在【服务与运营】分组，权限码 ``cms.campaign.manage``（查看用
``cms.campaign.view``），与轮播图/通知同一套逐模块口径。
"""

from django.db import transaction
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from content.campaign_services import (
    SECTION_LIMITS,
    CampaignCardError,
    create_card,
    move_card,
    update_card,
)
from content.models import HomeCampaignCard
from merchant_ops.api_utils import OpsAPIView


def _error(exc: CampaignCardError) -> StaffApiError:
    return StaffApiError(business_code=exc.code, message=exc.message, status_code=exc.status_code)


VALID_SECTIONS = ("campaign", "discovery")


def _resolve_section(request) -> str:
    section = str(request.query_params.get("section") or "campaign").strip().lower()
    if section not in VALID_SECTIONS:
        raise StaffApiError(
            business_code="SECTION_INVALID", message="卡片分区不正确。", status_code=400
        )
    return section


def _body_section(request) -> str:
    value = str((request.data or {}).get("section") or "campaign").strip().lower()
    if value not in VALID_SECTIONS:
        raise StaffApiError(
            business_code="SECTION_INVALID", message="卡片分区不正确。", status_code=400
        )
    return value


def _payload(card: HomeCampaignCard) -> dict:
    return {
        "id": str(card.public_id),
        "section": card.section,
        "title": card.title,
        "title_zh": card.title_zh,
        "subtitle": card.subtitle,
        "subtitle_zh": card.subtitle_zh,
        "image_url": card.image_url,
        "href": card.href,
        "sort_order": card.sort_order,
        "enabled": card.enabled,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }


class AdminCampaignCardsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def get(self, request):
        section = _resolve_section(request)
        rows = HomeCampaignCard.objects.filter(section=section).order_by("sort_order", "pk")
        return Response(
            {
                "section": section,
                "items": [_payload(card) for card in rows],
                "total": rows.count(),
                "max_cards": SECTION_LIMITS[section],
            }
        )

    def post(self, request):
        section = _body_section(request)
        try:
            with transaction.atomic():
                card = create_card(payload=request.data or {}, section=section)
        except CampaignCardError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CAMPAIGN_CARD_CREATED",
            # audit 的 target_type 保留原名，分区信息放在 after_state 里
            target_type="home_campaign_card",
            target_id=str(card.public_id),
            reason="",
            before_state={},
            after_state={"section": section, "title": card.title, "href": card.href},
        )
        return Response({"card": _payload(card)}, status=201)


class AdminCampaignCardDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def _get(self, public_id):
        return HomeCampaignCard.objects.filter(public_id=public_id).first()

    def get(self, request, public_id):
        card = self._get(public_id)
        if card is None:
            raise StaffApiError(
                business_code="CARD_NOT_FOUND", message="卡片不存在。", status_code=404
            )
        return Response({"card": _payload(card)})

    def patch(self, request, public_id):
        card = self._get(public_id)
        if card is None:
            raise StaffApiError(
                business_code="CARD_NOT_FOUND", message="卡片不存在。", status_code=404
            )
        before = {
            "title": card.title,
            "subtitle": card.subtitle,
            "href": card.href,
            "enabled": card.enabled,
        }
        try:
            card = update_card(card, payload=request.data or {})
        except CampaignCardError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CAMPAIGN_CARD_UPDATED",
            target_type="home_campaign_card",
            target_id=str(card.public_id),
            reason="",
            before_state=before,
            after_state={
                "title": card.title,
                "subtitle": card.subtitle,
                "href": card.href,
                "enabled": card.enabled,
            },
        )
        return Response({"card": _payload(card)})

    def delete(self, request, public_id):
        card = self._get(public_id)
        if card is None:
            raise StaffApiError(
                business_code="CARD_NOT_FOUND", message="卡片不存在。", status_code=404
            )
        title = card.title
        card.delete()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CAMPAIGN_CARD_DELETED",
            target_type="home_campaign_card",
            target_id=str(public_id),
            reason="",
            before_state={"title": title},
            after_state={},
        )
        return Response({"deleted": True}, status=200)


class AdminCampaignCardActionsView(OpsAPIView):
    """排序（上移/下移）与启用开关。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.campaign.manage"]
    view_permissions = ["cms.campaign.view"]

    def post(self, request, public_id):
        card = HomeCampaignCard.objects.filter(public_id=public_id).first()
        if card is None:
            raise StaffApiError(
                business_code="CARD_NOT_FOUND", message="卡片不存在。", status_code=404
            )
        payload = request.data or {}
        action = str(payload.get("action") or "").strip().lower()
        try:
            if action == "move":
                move_card(card, direction=payload.get("direction"))
            elif action == "toggle":
                card.enabled = not card.enabled
                card.save(update_fields=["enabled", "updated_at"])
            else:
                raise StaffApiError(
                    business_code="ACTION_INVALID", message="不支持的操作。", status_code=400
                )
        except CampaignCardError as exc:
            raise _error(exc) from exc
        return Response({"card": _payload(card)})
