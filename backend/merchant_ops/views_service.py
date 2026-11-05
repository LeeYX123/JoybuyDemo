"""A08 售后处理 / A09 平台活动与推荐返佣。"""

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import (
    OpsAPIView,
    date_str,
    iso,
    money_str,
    paginate,
    parse_amount,
    parse_date,
    require,
)
from merchant_ops.models import (
    AfterSale,
    AfterSaleEvent,
    MerchantActivity,
    MerchantActivityParticipation,
    MerchantReferral,
    ReferralCommission,
    ReferralProgram,
)
from merchant_ops.services import (
    append_after_sale_event,
    calculate_commissions,
    pay_commission,
    previous_period,
)

DECISION_STATE = {
    AfterSale.Decision.INVESTIGATE: AfterSale.State.PLATFORM,
    AfterSale.Decision.COMPLETE: AfterSale.State.COMPLETED,
    AfterSale.Decision.REJECT_RETURN: AfterSale.State.REJECTED,
}


# --------------------------------------------------------------------------
# A08 售后
# --------------------------------------------------------------------------


def _after_sale_payload(record: AfterSale, *, detail=False) -> dict:
    payload = {
        "id": str(record.public_id),
        "merchant": {
            "id": str(record.merchant.public_id),
            "name": record.merchant.display_name,
        },
        "order_id": str(record.order.public_id),
        "kind": record.kind,
        "state": record.state,
        "issue": record.issue,
        "progress": record.progress,
        "result": record.result,
        "platform_decision": record.platform_decision,
        "proof": list(record.proof or []),
        "created_at": iso(record.created_at),
        "completed_at": iso(record.completed_at),
    }
    if detail:
        payload["events"] = [
            {
                "id": event.pk,
                "actor": event.actor,
                "actor_label": event.actor_label,
                "action": event.action,
                "content": event.content,
                "created_at": iso(event.created_at),
            }
            for event in record.events.all()
        ]
        payload["order_status"] = record.order.status
    return payload


class AdminAfterSalesView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["aftersales.manage"]
    view_permissions = ["aftersales.view"]

    def get(self, request):
        queryset = AfterSale.objects.select_related("merchant", "order")
        state = (request.query_params.get("state") or "").strip().upper()
        if state and state != "ALL":
            queryset = queryset.filter(state=state)
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind and kind != "ALL":
            queryset = queryset.filter(kind=kind)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(merchant__display_name__icontains=query) | Q(issue__icontains=query)
            )
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response({"items": [_after_sale_payload(row) for row in rows], **meta})


class AdminAfterSaleDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["aftersales.manage"]
    view_permissions = ["aftersales.view"]

    def _get(self, public_id):
        record = (
            AfterSale.objects.select_related("merchant", "order")
            .prefetch_related("events")
            .filter(public_id=public_id)
            .first()
        )
        if record is None:
            raise StaffApiError(
                business_code="AFTER_SALE_NOT_FOUND", message="售后单不存在。", status_code=404
            )
        return record

    def get(self, request, public_id):
        return Response({"after_sale": _after_sale_payload(self._get(public_id), detail=True)})


class AdminAfterSaleActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["aftersales.manage"]
    view_permissions = ["aftersales.view"]

    def post(self, request, public_id):
        record = (
            AfterSale.objects.select_related("merchant", "order")
            .filter(public_id=public_id)
            .first()
        )
        if record is None:
            raise StaffApiError(
                business_code="AFTER_SALE_NOT_FOUND", message="售后单不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {"state": record.state}

        if action == "decide":
            decision = (payload.get("decision") or "").strip().upper()
            if decision not in DECISION_STATE:
                raise StaffApiError(
                    business_code="DECISION_INVALID",
                    message="请选择有效的处理结论。",
                    status_code=400,
                )
            if record.state in {AfterSale.State.COMPLETED, AfterSale.State.REJECTED}:
                raise StaffApiError(
                    business_code="AFTER_SALE_CLOSED",
                    message="该售后已结束，不能重复处理。",
                    status_code=409,
                )
            if (
                decision == AfterSale.Decision.COMPLETE
                and record.kind == AfterSale.Kind.RETURN
                and record.order.status == "COMPLETED"
            ):
                raise StaffApiError(
                    business_code="RETURN_AFTER_RECEIVED",
                    message="订单已确认收货，不能再完成退货处理。",
                    status_code=409,
                )
            record.platform_decision = decision
            record.state = DECISION_STATE[decision]
            if decision == AfterSale.Decision.COMPLETE:
                record.completed_at = timezone.now()
                record.result = (payload.get("result") or "").strip() or record.result
            append_after_sale_event(
                record,
                actor_type=AfterSaleEvent.Actor.PLATFORM,
                actor_label=request.staff_account.display_name,
                action=f"平台结论：{record.get_platform_decision_display()}",
                content=(payload.get("result") or "").strip(),
            )
        elif action == "update_progress":
            record.progress = (payload.get("progress") or "").strip()[:255]
            if record.state == AfterSale.State.PENDING:
                record.state = AfterSale.State.PROCESSING
            append_after_sale_event(
                record,
                actor_type=AfterSaleEvent.Actor.PLATFORM,
                actor_label=request.staff_account.display_name,
                action="更新处理进度",
                content=record.progress,
            )
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )

        record.save()
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"AFTER_SALE_{action.upper()}",
            target_type="after_sale",
            target_id=str(record.public_id),
            reason="",
            before_state=before,
            after_state={"state": record.state, "decision": record.platform_decision},
            tenant_type="merchant",
            tenant_id=str(record.merchant_id),
        )
        record.refresh_from_db()
        return Response({"after_sale": _after_sale_payload(record, detail=True)})


# --------------------------------------------------------------------------
# A09 平台活动
# --------------------------------------------------------------------------


def _activity_payload(activity: MerchantActivity, *, participants=None) -> dict:
    return {
        "id": str(activity.public_id),
        "title": activity.title,
        "kind": activity.kind,
        "state": activity.state,
        "start": date_str(activity.start_date),
        "end": date_str(activity.end_date),
        "description": activity.description,
        "image": activity.image_url,
        "is_referral": activity.is_referral,
        "sort_order": activity.sort_order,
        "participants": participants
        if participants is not None
        else activity.participations.count(),
        "created_at": iso(activity.created_at),
    }


class AdminActivitiesView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def get(self, request):
        queryset = MerchantActivity.objects.all()
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind in {"PERMANENT", "LIMITED"}:
            queryset = queryset.filter(kind=kind)
        state = (request.query_params.get("state") or "").strip().upper()
        if state in {"ONGOING", "ENDED"}:
            queryset = queryset.filter(state=state)
        rows, meta = paginate(queryset, request)
        return Response({"items": [_activity_payload(row) for row in rows], **meta})

    def post(self, request):
        payload = request.data or {}
        title = require(payload, "title", label="活动标题").strip()
        start = parse_date(require(payload, "start", label="开始日期"), field="开始日期")
        end = parse_date(payload.get("end"), field="结束日期")
        if end and end < start:
            raise StaffApiError(
                business_code="DATE_ORDER_INVALID",
                message="结束日期不能早于开始日期。",
                status_code=400,
            )
        is_referral = bool(payload.get("is_referral"))
        if is_referral and MerchantActivity.objects.filter(is_referral=True).exists():
            raise StaffApiError(
                business_code="REFERRAL_ACTIVITY_EXISTS",
                message="推荐返佣常驻活动已存在。",
                status_code=409,
            )
        activity = MerchantActivity.objects.create(
            title=title,
            kind=payload.get("kind")
            if payload.get("kind") in dict(MerchantActivity.Kind.choices)
            else MerchantActivity.Kind.PERMANENT,
            start_date=start,
            end_date=end,
            description=(payload.get("description") or "").strip(),
            image_url=(payload.get("image") or "").strip(),
            is_referral=is_referral,
            sort_order=int(payload.get("sort_order") or 0),
        )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_CREATED",
            target_type="merchant_activity",
            target_id=str(activity.public_id),
            reason="",
            before_state={},
            after_state={"title": activity.title, "kind": activity.kind},
        )
        return Response({"activity": _activity_payload(activity)}, status=201)


class AdminActivityDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def _get(self, public_id):
        activity = MerchantActivity.objects.filter(public_id=public_id).first()
        if activity is None:
            raise StaffApiError(
                business_code="ACTIVITY_NOT_FOUND", message="活动不存在。", status_code=404
            )
        return activity

    def patch(self, request, public_id):
        activity = self._get(public_id)
        payload = request.data or {}
        before = {"title": activity.title, "state": activity.state}
        if "title" in payload:
            title = (payload.get("title") or "").strip()
            if not title:
                raise StaffApiError(
                    business_code="TITLE_REQUIRED", message="活动标题不能为空。", status_code=400
                )
            activity.title = title
        if "kind" in payload and payload["kind"] in dict(MerchantActivity.Kind.choices):
            activity.kind = payload["kind"]
        if "start" in payload:
            activity.start_date = parse_date(payload.get("start"), field="开始日期")
        if "end" in payload:
            activity.end_date = parse_date(payload.get("end"), field="结束日期")
        if activity.end_date and activity.end_date < activity.start_date:
            raise StaffApiError(
                business_code="DATE_ORDER_INVALID",
                message="结束日期不能早于开始日期。",
                status_code=400,
            )
        if "description" in payload:
            activity.description = (payload.get("description") or "").strip()
        if "image" in payload:
            activity.image_url = (payload.get("image") or "").strip()
        if "sort_order" in payload:
            activity.sort_order = int(payload.get("sort_order") or 0)
        activity.save()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="ACTIVITY_UPDATED",
            target_type="merchant_activity",
            target_id=str(activity.public_id),
            reason="",
            before_state=before,
            after_state={"title": activity.title, "state": activity.state},
        )
        return Response({"activity": _activity_payload(activity)})


class AdminActivityActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def post(self, request, public_id):
        activity = MerchantActivity.objects.filter(public_id=public_id).first()
        if activity is None:
            raise StaffApiError(
                business_code="ACTIVITY_NOT_FOUND", message="活动不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        before = {"state": activity.state}
        if action == "end":
            activity.state = MerchantActivity.State.ENDED
        elif action == "reopen":
            activity.state = MerchantActivity.State.ONGOING
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        activity.save(update_fields=["state", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"ACTIVITY_{action.upper()}",
            target_type="merchant_activity",
            target_id=str(activity.public_id),
            reason="",
            before_state=before,
            after_state={"state": activity.state},
        )
        return Response({"activity": _activity_payload(activity)})


class AdminActivityParticipationsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def get(self, request, public_id):
        activity = MerchantActivity.objects.filter(public_id=public_id).first()
        if activity is None:
            raise StaffApiError(
                business_code="ACTIVITY_NOT_FOUND", message="活动不存在。", status_code=404
            )
        rows, meta = paginate(
            MerchantActivityParticipation.objects.select_related("merchant")
            .filter(activity=activity)
            .order_by("-joined_at"),
            request,
        )
        return Response(
            {
                "items": [
                    {
                        "id": str(row.merchant.public_id),
                        "merchant": row.merchant.display_name,
                        "joined_at": iso(row.joined_at),
                        "exposure_added": row.exposure_added,
                        "status": activity.state,
                    }
                    for row in rows
                ],
                **meta,
            }
        )

    def post(self, request, public_id):
        """管理端为商家补录参与关系（正常由商家端自行参与）。"""

        activity = MerchantActivity.objects.filter(public_id=public_id).first()
        if activity is None:
            raise StaffApiError(
                business_code="ACTIVITY_NOT_FOUND", message="活动不存在。", status_code=404
            )
        payload = request.data or {}
        merchant_id = require(payload, "merchant_id", label="商家")
        from merchants.models import Merchant

        merchant = Merchant.objects.filter(public_id=merchant_id).first()
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        participation, created = MerchantActivityParticipation.objects.get_or_create(
            activity=activity, merchant=merchant
        )
        return Response(
            {
                "participation": {
                    "id": str(merchant.public_id),
                    "merchant": merchant.display_name,
                    "joined_at": iso(participation.joined_at),
                    "created": created,
                }
            },
            status=201 if created else 200,
        )


# --------------------------------------------------------------------------
# A09 推荐返佣
# --------------------------------------------------------------------------


class AdminReferralProgramView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def get(self, request):
        program = ReferralProgram.load()
        return Response(
            {
                "program": {
                    "tiers": program.tiers,
                    "valid_months": program.valid_months,
                    "updated_at": iso(program.updated_at),
                }
            }
        )

    def put(self, request):
        payload = request.data or {}
        raw_tiers = payload.get("tiers")
        if not isinstance(raw_tiers, list) or not raw_tiers:
            raise StaffApiError(
                business_code="TIERS_REQUIRED", message="至少需要一个返佣档位。", status_code=400
            )
        tiers = []
        previous_min = None
        for entry in raw_tiers:
            tier_min = parse_amount(entry.get("min"), field="档位最低金额")
            rate = parse_amount(entry.get("rate"), field="返佣比例")
            if tier_min < 0 or rate < 0 or rate > 100:
                raise StaffApiError(
                    business_code="TIER_RANGE_INVALID",
                    message="档位金额不能为负，比例必须在 0 到 100 之间。",
                    status_code=400,
                )
            if previous_min is not None and tier_min <= previous_min:
                raise StaffApiError(
                    business_code="TIER_NOT_INCREASING",
                    message="档位金额必须严格递增。",
                    status_code=400,
                )
            previous_min = tier_min
            tiers.append({"min": str(tier_min), "rate": str(rate)})
        if Decimal(tiers[0]["min"]) != 0:
            raise StaffApiError(
                business_code="TIER_FIRST_NOT_ZERO",
                message="首档最低金额必须为 0。",
                status_code=400,
            )
        months = int(payload.get("valid_months") or 0)
        if months <= 0:
            raise StaffApiError(
                business_code="VALID_MONTHS_INVALID",
                message="返佣有效月数必须大于 0。",
                status_code=400,
            )

        program = ReferralProgram.load()
        before = {"tiers": program.tiers, "valid_months": program.valid_months}
        program.tiers = tiers
        program.valid_months = months
        program.updated_by = request.staff_account
        program.save()
        record_audit(
            request=request,
            actor=request.staff_account,
            action="REFERRAL_PROGRAM_UPDATED",
            target_type="referral_program",
            target_id=str(program.pk),
            reason="",
            before_state=before,
            after_state={"tiers": program.tiers, "valid_months": program.valid_months},
        )
        return Response(
            {
                "program": {
                    "tiers": program.tiers,
                    "valid_months": program.valid_months,
                    "updated_at": iso(program.updated_at),
                }
            }
        )


class AdminReferralCalculateView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def post(self, request):
        payload = request.data or {}
        period = (payload.get("period") or previous_period()).strip()
        if len(period) != 7 or period[4] != "-":
            raise StaffApiError(
                business_code="PERIOD_INVALID",
                message="核算月份格式必须为 YYYY-MM。",
                status_code=400,
            )
        commissions = calculate_commissions(period)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="REFERRAL_CALCULATED",
            target_type="referral_commission",
            target_id=period,
            reason="",
            before_state={},
            after_state={"period": period, "count": len(commissions)},
        )
        return Response({"period": period, "count": len(commissions)})


def _commission_payload(commission: ReferralCommission) -> dict:
    return {
        "id": str(commission.public_id),
        "period": commission.period,
        "referrer": {
            "id": str(commission.referral.referrer.public_id),
            "name": commission.referral.referrer.display_name,
        },
        "referee": {
            "id": str(commission.referral.referee.public_id),
            "name": commission.referral.referee.display_name,
        },
        "shipped_amount": money_str(commission.shipped_amount),
        "rate": str(commission.rate),
        "amount": money_str(commission.amount),
        "state": commission.state,
        "calculated_at": iso(commission.calculated_at),
        "paid_at": iso(commission.paid_at),
    }


class AdminReferralCommissionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def get(self, request):
        queryset = ReferralCommission.objects.select_related(
            "referral__referrer", "referral__referee"
        )
        state = (request.query_params.get("state") or "").strip().upper()
        if state and state != "ALL":
            queryset = queryset.filter(state=state)
        period = (request.query_params.get("period") or "").strip()
        if period:
            queryset = queryset.filter(period=period)
        rows, meta = paginate(queryset, request)
        return Response({"items": [_commission_payload(row) for row in rows], **meta})


class AdminReferralCommissionActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def post(self, request, public_id):
        commission = ReferralCommission.objects.filter(public_id=public_id).first()
        if commission is None:
            raise StaffApiError(
                business_code="COMMISSION_NOT_FOUND", message="返佣记录不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        if action != "pay":
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        before = {"state": commission.state}
        commission = pay_commission(commission, actor=request.staff_account)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="REFERRAL_COMMISSION_PAID",
            target_type="referral_commission",
            target_id=str(commission.public_id),
            reason="",
            before_state=before,
            after_state={"state": commission.state, "amount": str(commission.amount)},
            tenant_type="merchant",
            tenant_id=str(commission.referral.referrer_id),
        )
        commission.refresh_from_db()
        return Response({"commission": _commission_payload(commission)})


class AdminReferralsView(OpsAPIView):
    """推荐关系列表：谁推荐了谁、绑定时间与推荐码。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["activities.manage"]
    view_permissions = ["activities.view"]

    def get(self, request):
        queryset = MerchantReferral.objects.select_related("referrer", "referee")
        rows, meta = paginate(queryset.order_by("-created_at"), request)
        return Response(
            {
                "items": [
                    {
                        "id": str(row.referee.public_id),
                        "referrer": {
                            "id": str(row.referrer.public_id),
                            "name": row.referrer.display_name,
                            "code": row.referrer.referral_code,
                        },
                        "referee": {
                            "id": str(row.referee.public_id),
                            "name": row.referee.display_name,
                        },
                        "code_used": row.code_used,
                        "created_at": iso(row.created_at),
                    }
                    for row in rows
                ],
                **meta,
            }
        )
