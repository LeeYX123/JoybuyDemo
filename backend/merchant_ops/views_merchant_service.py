"""商家端 M07 售后中心 / M08 平台活动中心与推荐返佣。"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from audit.services import record_audit
from merchant_ops.api_utils import date_str, iso, money_str, paginate
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.models import (
    AfterSale,
    AfterSaleEvent,
    MerchantActivity,
    MerchantActivityParticipation,
    MerchantReferral,
    ReferralCommission,
    ReferralProgram,
)
from merchant_ops.services import append_after_sale_event
from merchants.services import ensure_referral_code

AFTER_SALE_KINDS = (AfterSale.Kind.COMPLAINT, AfterSale.Kind.RETURN)


def _after_sale_payload(record: AfterSale, *, detail: bool = False) -> dict:
    payload = {
        "id": str(record.public_id),
        "order_id": str(record.order.public_id),
        "kind": record.kind,
        "state": record.state,
        "issue": record.issue,
        "progress": record.progress,
        "result": record.result,
        "platform_decision": record.platform_decision,
        "proof": list(record.proof or []),
        "currency": record.currency,
        "created_at": iso(record.created_at),
        "completed_at": iso(record.completed_at),
        "readonly": record.state in (AfterSale.State.COMPLETED, AfterSale.State.REJECTED),
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
        payload["order"] = {
            "id": str(record.order.public_id),
            "status": record.order.status,
            "paid": bool(getattr(record.order, "paid_at", None)),
        }
        item = record.merchant_order.items.first() if record.merchant_order_id else None
        payload["product"] = (
            {
                "title": item.title,
                "quantity": item.quantity,
                "unit_price": money_str(item.unit_price),
            }
            if item
            else None
        )
    return payload


class MerchantAfterSalesView(MerchantAPIView):
    permission_any = ("merchant.aftersales.manage",)

    def get(self, request):
        queryset = AfterSale.objects.select_related("order", "merchant_order").filter(
            merchant=request.merchant
        )
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind and kind != "ALL" and kind in AFTER_SALE_KINDS:
            queryset = queryset.filter(kind=kind)
        state = (request.query_params.get("state") or "").strip().upper()
        if state and state != "ALL":
            queryset = queryset.filter(state=state)
        query = (request.query_params.get("q") or "").strip()
        if query:
            condition = Q(issue__icontains=query) | Q(progress__icontains=query)
            try:
                import uuid as uuid_module

                condition |= Q(public_id=uuid_module.UUID(query))
                condition |= Q(order__public_id=uuid_module.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition).distinct()
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        counts = {
            "ALL": AfterSale.objects.filter(merchant=request.merchant).count(),
            AfterSale.Kind.COMPLAINT: AfterSale.objects.filter(
                merchant=request.merchant, kind=AfterSale.Kind.COMPLAINT
            ).count(),
            AfterSale.Kind.RETURN: AfterSale.objects.filter(
                merchant=request.merchant, kind=AfterSale.Kind.RETURN
            ).count(),
        }
        return Response(
            {"items": [_after_sale_payload(record) for record in rows], "counts": counts, **meta}
        )


class MerchantAfterSaleDetailView(MerchantAPIView):
    permission_any = ("merchant.aftersales.manage",)

    def get(self, request, public_id):
        record = _resolve_after_sale(request, public_id)
        return Response({"after_sale": _after_sale_payload(record, detail=True)})


def _resolve_after_sale(request, public_id) -> AfterSale:
    record = (
        AfterSale.objects.select_related("order", "merchant_order")
        .filter(merchant=request.merchant, public_id=public_id)
        .first()
    )
    if record is None:
        raise StaffApiError(
            business_code="AFTER_SALE_NOT_FOUND",
            message="售后单不存在或不属于当前店铺。",
            status_code=404,
        )
    return record


class MerchantAfterSaleActionsView(MerchantAPIView):
    permission_any = ("merchant.aftersales.manage",)

    def post(self, request, public_id):
        record = _resolve_after_sale(request, public_id)
        payload = request.data or {}
        action = str(payload.get("action") or "").strip().lower()

        if record.state in (AfterSale.State.COMPLETED, AfterSale.State.REJECTED):
            raise StaffApiError(
                business_code="AFTER_SALE_CLOSED",
                message="该售后单已关闭，不能再处理。",
                status_code=400,
            )

        if action == "progress":
            note = str(payload.get("progress") or "").strip()
            if not note:
                raise StaffApiError(
                    business_code="PROGRESS_REQUIRED", message="请填写处理进度。", status_code=400
                )
            record.progress = note[:255]
            if record.state == AfterSale.State.PENDING:
                record.state = AfterSale.State.PROCESSING
            record.save(update_fields=["progress", "state", "updated_at"])
            append_after_sale_event(
                record,
                actor_type=AfterSaleEvent.Actor.MERCHANT,
                action="更新处理进度",
                content=note,
            )
        elif action == "proof":
            # 售后凭证：只接受本服务上传产生的 /media/ 路径或 http(s) 链接，
            # 前端上传后用返回的 URL 提交，避免把外部乱链写进库里。
            images = payload.get("images")
            if not isinstance(images, list):
                raise StaffApiError(
                    business_code="PROOF_INVALID",
                    message="凭证必须是图片地址数组。",
                    status_code=400,
                )
            cleaned = []
            for item in images:
                url = str(item or "").strip()
                if not url:
                    continue
                if not (
                    url.startswith("/media/")
                    or url.startswith("http://")
                    or url.startswith("https://")
                ):
                    raise StaffApiError(
                        business_code="PROOF_URL_INVALID",
                        message="凭证地址不合法，请通过上传按钮添加。",
                        status_code=400,
                    )
                cleaned.append(url)
            if len(cleaned) > 5:
                raise StaffApiError(
                    business_code="PROOF_TOO_MANY", message="凭证最多 5 张。", status_code=400
                )
            record.proof = cleaned
            record.save(update_fields=["proof", "updated_at"])
            append_after_sale_event(
                record,
                actor_type=AfterSaleEvent.Actor.MERCHANT,
                action="更新凭证",
                content=f"共 {len(cleaned)} 张",
            )
        elif action == "escalate":
            if record.state == AfterSale.State.PLATFORM:
                raise StaffApiError(
                    business_code="AFTER_SALE_ALREADY_PLATFORM",
                    message="该售后单已在平台介入中。",
                    status_code=400,
                )
            note = str(payload.get("note") or "").strip()
            record.state = AfterSale.State.PLATFORM
            record.save(update_fields=["state", "updated_at"])
            append_after_sale_event(
                record,
                actor_type=AfterSaleEvent.Actor.MERCHANT,
                action="申请平台介入",
                content=note,
            )
        elif action == "complete":
            # 用户确认收货（子单已完成）后不得再办理退货类售后；
            # 投诉咨询不受这条限制。
            if (
                record.kind == AfterSale.Kind.RETURN
                and record.merchant_order_id
                and record.merchant_order.status == "COMPLETED"
            ):
                raise StaffApiError(
                    business_code="RETURN_AFTER_RECEIPT_BLOCKED",
                    message="用户已确认收货，不能办理退货类售后。",
                    status_code=400,
                )
            result = str(payload.get("result") or "").strip()
            if not result:
                raise StaffApiError(
                    business_code="RESULT_REQUIRED", message="请填写处理结果。", status_code=400
                )
            record.result = result
            record.state = AfterSale.State.COMPLETED
            record.completed_at = timezone.now()
            record.save(update_fields=["result", "state", "completed_at", "updated_at"])
            append_after_sale_event(
                record, actor_type=AfterSaleEvent.Actor.MERCHANT, action="完成处理", content=result
            )
        else:
            raise StaffApiError(
                business_code="ACTION_INVALID", message="不支持的处理动作。", status_code=400
            )

        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_AFTER_SALE_HANDLED",
            target_type="after_sale",
            target_id=str(record.public_id),
            reason="",
            before_state={},
            after_state={"action": action, "state": record.state},
            tenant_type="MERCHANT",
            tenant_id=str(request.merchant.public_id),
        )
        record.refresh_from_db()
        return Response({"after_sale": _after_sale_payload(record, detail=True)})


# --------------------------------------------------------------------------
# M08 活动与推荐返佣
# --------------------------------------------------------------------------


def _activity_payload(activity: MerchantActivity, *, joined: bool, joined_at=None) -> dict:
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
        "joined": joined,
        "joined_at": iso(joined_at),
        "participants": activity.participations.count(),
    }


class MerchantActivitiesView(MerchantAPIView):
    permission_any = ("merchant.activities.view",)

    def get(self, request):
        queryset = MerchantActivity.objects.filter(is_referral=False)
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind in (MerchantActivity.Kind.PERMANENT, MerchantActivity.Kind.LIMITED):
            queryset = queryset.filter(kind=kind)
        joined_ids = dict(
            MerchantActivityParticipation.objects.filter(
                merchant=request.merchant, activity__in=queryset
            ).values_list("activity_id", "joined_at")
        )
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response(
            {
                "items": [
                    _activity_payload(
                        activity,
                        joined=activity.pk in joined_ids,
                        joined_at=joined_ids.get(activity.pk),
                    )
                    for activity in rows
                ],
                **meta,
            }
        )


class MerchantActivityDetailView(MerchantAPIView):
    permission_any = ("merchant.activities.view",)

    def get(self, request, public_id):
        activity = MerchantActivity.objects.filter(public_id=public_id, is_referral=False).first()
        if activity is None:
            raise StaffApiError(
                business_code="ACTIVITY_NOT_FOUND", message="活动不存在。", status_code=404
            )
        participation = MerchantActivityParticipation.objects.filter(
            activity=activity, merchant=request.merchant
        ).first()
        payload = _activity_payload(
            activity,
            joined=participation is not None,
            joined_at=participation.joined_at if participation else None,
        )
        payload["exposure_added"] = participation.exposure_added if participation else 0
        return Response({"activity": payload})


class MerchantActivityJoinView(MerchantAPIView):
    permission_any = ("merchant.activities.view",)

    def post(self, request, public_id):
        activity = MerchantActivity.objects.filter(public_id=public_id, is_referral=False).first()
        if activity is None:
            raise StaffApiError(
                business_code="ACTIVITY_NOT_FOUND", message="活动不存在。", status_code=404
            )
        if activity.state != MerchantActivity.State.ONGOING:
            raise StaffApiError(
                business_code="ACTIVITY_ENDED", message="活动已结束，不能参与。", status_code=400
            )
        participation, created = MerchantActivityParticipation.objects.get_or_create(
            activity=activity, merchant=request.merchant
        )
        if created:
            record_audit(
                request=request,
                actor=request.staff_account,
                action="MERCHANT_ACTIVITY_JOINED",
                target_type="merchant_activity",
                target_id=str(activity.public_id),
                reason="",
                before_state={},
                after_state={"merchant": str(request.merchant.public_id)},
                tenant_type="MERCHANT",
                tenant_id=str(request.merchant.public_id),
            )
        return Response(
            {
                "joined": True,
                "created": created,
                "activity": _activity_payload(
                    activity, joined=True, joined_at=participation.joined_at
                ),
            }
        )


class MerchantReferralView(MerchantAPIView):
    permission_any = ("merchant.activities.view",)

    def get(self, request):
        merchant = request.merchant
        code = ensure_referral_code(merchant)
        program = ReferralProgram.load()
        commissions = (
            ReferralCommission.objects.select_related("referral__referee", "referral__referrer")
            .filter(referral__referrer=merchant)
            .order_by("-period", "-pk")
        )
        referrals = MerchantReferral.objects.filter(referrer=merchant).select_related("referee")
        return Response(
            {
                "referral_code": code,
                "valid_months": program.valid_months,
                "tiers": list(program.tiers or []),
                "stats": {
                    "referred_count": referrals.count(),
                    "paid_amount": money_str(
                        sum(
                            c.amount
                            for c in commissions
                            if c.state == ReferralCommission.State.PAID
                        )
                    ),
                    "pending_amount": money_str(
                        sum(
                            c.amount
                            for c in commissions
                            if c.state == ReferralCommission.State.PENDING_PAY
                        )
                    ),
                },
                "referrals": [
                    {
                        "merchant_id": str(item.referee.public_id),
                        "name": item.referee.display_name,
                        "joined_at": iso(item.created_at),
                        "code_used": item.code_used,
                    }
                    for item in referrals[:50]
                ],
                "commissions": [
                    {
                        "id": str(commission.public_id),
                        "period": commission.period,
                        "referee": commission.referral.referee.display_name,
                        "shipped_amount": money_str(commission.shipped_amount),
                        "rate": str(commission.rate),
                        "amount": money_str(commission.amount),
                        "state": commission.state,
                        "calculated_at": iso(commission.calculated_at),
                        "paid_at": iso(commission.paid_at),
                    }
                    for commission in commissions[:100]
                ],
            }
        )
