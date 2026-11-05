"""A15 商家关注与曝光：只做增量调整，不承载平台规则配置。"""

from django.db.models import Q
from rest_framework.response import Response

from accounts_staff.permissions import StaffRbacPermission
from audit.models import AuditLog
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, paginate, parse_positive_int
from merchants.models import Merchant
from merchants.services import add_exposure, add_followers


def _row(merchant: Merchant) -> dict:
    return {
        "id": str(merchant.public_id),
        "name": merchant.display_name,
        "status": merchant.onboarding_status,
        "followers": merchant.followers,
        "follow_delta": merchant.follow_delta,
        "follow_day": merchant.follow_day.isoformat() if merchant.follow_day else None,
        "exposure": merchant.exposure,
    }


class AdminGrowthView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.growth.manage"]
    view_permissions = ["merchants.growth.view"]

    def get(self, request):
        queryset = Merchant.objects.exclude(merchant_type=Merchant.Type.IMPORT_FALLBACK).exclude(
            onboarding_status=Merchant.OnboardingStatus.DRAFT
        )
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(display_name__icontains=query) | Q(slug__icontains=query))
        rows, meta = paginate(queryset.order_by("-followers", "-pk"), request)
        return Response({"items": [_row(merchant) for merchant in rows], **meta})


class AdminGrowthActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.growth.manage"]

    def post(self, request, public_id):
        from accounts_staff.api_exceptions import StaffApiError

        merchant = Merchant.objects.filter(public_id=public_id).first()
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {"followers": merchant.followers, "exposure": merchant.exposure}

        if action == "add_followers":
            count = parse_positive_int(payload.get("count"), field="新增关注")
            merchant = add_followers(merchant, count=count)
            audit_action = "MERCHANT_FOLLOWERS_ADDED"
        elif action == "add_exposure":
            count = parse_positive_int(payload.get("count"), field="新增曝光")
            merchant = add_exposure(merchant, count=count)
            audit_action = "MERCHANT_EXPOSURE_ADDED"
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )

        record_audit(
            request=request,
            actor=request.staff_account,
            action=audit_action,
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason="",
            before_state=before,
            after_state={"followers": merchant.followers, "exposure": merchant.exposure},
            tenant_type="merchant",
            tenant_id=str(merchant.public_id),
        )
        return Response({"merchant": _row(merchant)})


class AdminGrowthRecordsView(OpsAPIView):
    """调整记录：直接读审计日志（关注/曝光调整本就要求留痕）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.growth.manage"]
    view_permissions = ["merchants.growth.view"]

    def get(self, request):
        queryset = AuditLog.objects.select_related("actor").filter(
            action__in=["MERCHANT_FOLLOWERS_ADDED", "MERCHANT_EXPOSURE_ADDED"]
        )
        merchant_id = (request.query_params.get("merchant") or "").strip()
        if merchant_id:
            queryset = queryset.filter(target_id=merchant_id)
        rows, meta = paginate(queryset.order_by("-created_at"), request)
        return Response(
            {
                "items": [
                    {
                        "id": str(log.pk),
                        "occurred_at": iso(log.created_at),
                        "operator": log.actor.display_name if log.actor else "系统",
                        "action": log.action,
                        "target_id": log.target_id,
                        "before": log.before_state,
                        "after": log.after_state,
                    }
                    for log in rows
                ],
                **meta,
            }
        )
