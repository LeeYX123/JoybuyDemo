"""平台管理后台：频道页活动卡片（13.2【品类页卡片展示】）配置。

与频道页 banner 同一套逐模块口径：权限码 ``cms.channel_page_cards.manage``
（编辑）与 ``cms.channel_page_cards.view``（查看），写操作写审计日志。
频道维度用 ``channel_code`` 过滤，图片只接受本地 ``/media/`` 路径；
``link_url`` 按 13.8 存原值不限制不改写。
"""

from django.db import transaction
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from content.channel_page_card_services import (
    ChannelPageCardError,
    channel_options,
    create_card,
    move_card,
    serialize_card,
    update_card,
)
from content.models import ChannelPageCard
from merchant_ops.api_utils import OpsAPIView


def _error(exc: ChannelPageCardError) -> StaffApiError:
    return StaffApiError(business_code=exc.code, message=exc.message, status_code=exc.status_code)


def _find(public_id) -> ChannelPageCard:
    card = ChannelPageCard.objects.filter(public_id=public_id).first()
    if card is None:
        raise StaffApiError(
            business_code="CARD_NOT_FOUND", message="活动卡片不存在。", status_code=404
        )
    return card


class AdminChannelPageCardsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_page_cards.manage"]
    view_permissions = ["cms.channel_page_cards.view"]

    def get(self, request):
        channel_code = str(request.query_params.get("channel_code") or "").strip()
        rows = ChannelPageCard.objects.all()
        if channel_code:
            rows = rows.filter(channel_code=channel_code)
        rows = rows.order_by("channel_code", "group_index", "sort_order", "public_id")
        items = [serialize_card(row) for row in rows]
        return Response({"channel_code": channel_code, "items": items, "total": len(items)})

    def post(self, request):
        try:
            with transaction.atomic():
                card = create_card(payload=request.data or {})
        except ChannelPageCardError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_PAGE_CARD_CREATED",
            target_type="channel_page_card",
            target_id=str(card.public_id),
            reason="",
            before_state={},
            after_state={
                "channel_code": card.channel_code,
                "image_url": card.image_url,
                "link_url": card.link_url,
                "layout": card.layout,
            },
        )
        return Response({"card": serialize_card(card)}, status=201)


class AdminChannelPageCardChannelsView(OpsAPIView):
    """频道下拉：有 minihome code 的一级类目（9 个频道）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_page_cards.manage"]
    view_permissions = ["cms.channel_page_cards.view"]

    def get(self, request):
        items = channel_options()
        return Response({"items": items, "total": len(items)})


class AdminChannelPageCardDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_page_cards.manage"]
    view_permissions = ["cms.channel_page_cards.view"]

    def get(self, request, public_id):
        return Response({"card": serialize_card(_find(public_id))})

    def patch(self, request, public_id):
        card = _find(public_id)
        before = serialize_card(card)
        try:
            card = update_card(card, payload=request.data or {})
        except ChannelPageCardError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_PAGE_CARD_UPDATED",
            target_type="channel_page_card",
            target_id=str(card.public_id),
            reason="",
            before_state=before,
            after_state=serialize_card(card),
        )
        return Response({"card": serialize_card(card)})

    def delete(self, request, public_id):
        card = _find(public_id)
        snapshot = serialize_card(card)
        card.delete()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_PAGE_CARD_DELETED",
            target_type="channel_page_card",
            target_id=str(public_id),
            reason="",
            before_state=snapshot,
            after_state={},
        )
        return Response({"deleted": True}, status=200)


class AdminChannelPageCardActionsView(OpsAPIView):
    """排序（上移/下移）与启用开关。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["cms.channel_page_cards.manage"]
    view_permissions = ["cms.channel_page_cards.view"]

    def post(self, request, public_id):
        card = _find(public_id)
        payload = request.data or {}
        action = str(payload.get("action") or "").strip().lower()
        try:
            if action == "move":
                move_card(card, direction=payload.get("direction"))
            elif action == "toggle":
                card.is_active = not card.is_active
                card.save(update_fields=["is_active", "updated_at"])
            else:
                raise StaffApiError(
                    business_code="ACTION_INVALID", message="不支持的操作。", status_code=400
                )
        except ChannelPageCardError as exc:
            raise _error(exc) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="CHANNEL_PAGE_CARD_ACTION",
            target_type="channel_page_card",
            target_id=str(card.public_id),
            reason="",
            before_state={},
            after_state={"action": action, "is_active": card.is_active},
        )
        return Response({"card": serialize_card(card)})
