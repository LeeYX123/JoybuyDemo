"""A17 操作日志：查询、变更详情与导出。"""

from django.db.models import Q
from rest_framework.response import Response

from accounts_staff.permissions import StaffRbacPermission
from audit.models import AuditLog
from merchant_ops.api_utils import OpsAPIView, csv_response, iso, paginate

MODULE_LABELS = {
    "merchant": "商家管理",
    "merchant_order": "订单管理",
    "merchant_withdrawal": "提现审核",
    "merchant_notification": "平台通知",
    "merchant_activity": "平台活动",
    "referral_commission": "推荐返佣",
    "referral_program": "返佣规则",
    "after_sale": "售后处理",
    "home_banner": "首页轮播图",
    "staff_account": "账号与权限",
    "buyer_account": "用户端管理",
    "support_conversation": "客服中心",
    "spu": "商品池",
    "offer": "商家商品",
}


def _payload(log: AuditLog) -> dict:
    return {
        "id": str(log.pk),
        "occurred_at": iso(log.created_at),
        "operator": log.actor.display_name if log.actor else "系统",
        "operator_email": log.actor.email if log.actor else "",
        "module": log.target_type,
        "module_label": MODULE_LABELS.get(log.target_type, log.target_type),
        "target": log.target_id,
        "action": log.action,
        "reason": log.reason,
        "before": log.before_state,
        "after": log.after_state,
        "ip_address": log.ip_address,
        "request_id": str(log.request_id) if log.request_id else None,
    }


def _filtered(request):
    queryset = AuditLog.objects.select_related("actor")
    query = (request.query_params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(action__icontains=query)
            | Q(target_id__icontains=query)
            | Q(actor__display_name__icontains=query)
            | Q(actor__email__icontains=query)
        )
    module = (request.query_params.get("module") or "").strip()
    if module:
        queryset = queryset.filter(target_type=module)
    action = (request.query_params.get("action") or "").strip()
    if action:
        queryset = queryset.filter(action__icontains=action)
    operator = (request.query_params.get("operator") or "").strip()
    if operator:
        queryset = queryset.filter(
            Q(actor__display_name__icontains=operator) | Q(actor__email__icontains=operator)
        )
    start = (request.query_params.get("start") or "").strip()
    end = (request.query_params.get("end") or "").strip()
    if start:
        queryset = queryset.filter(created_at__date__gte=start[:10])
    if end:
        queryset = queryset.filter(created_at__date__lte=end[:10])
    return queryset.order_by("-created_at", "-pk")


class AdminAuditLogsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["audit.logs.export"]
    view_permissions = ["audit.logs.view"]

    def get(self, request):
        rows, meta = paginate(_filtered(request), request)
        return Response({"items": [_payload(row) for row in rows], **meta})


class AdminAuditLogModulesView(OpsAPIView):
    """筛选下拉的模块选项（只列库里真实出现过的）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["audit.logs.export"]
    view_permissions = ["audit.logs.view"]

    def get(self, request):
        codes = (
            AuditLog.objects.values_list("target_type", flat=True)
            .distinct()
            .order_by("target_type")
        )
        return Response(
            {
                "items": [
                    {"code": code, "label": MODULE_LABELS.get(code, code)} for code in codes if code
                ]
            }
        )


class AdminAuditLogsExportView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["audit.logs.export"]

    def get(self, request):
        rows = [_payload(log) for log in _filtered(request)[:5000]]
        return csv_response(
            "audit-logs.csv",
            ["时间", "操作人", "模块", "业务对象", "动作", "备注"],
            [
                [
                    row["occurred_at"],
                    row["operator"],
                    row["module_label"],
                    row["target"],
                    row["action"],
                    row["reason"],
                ]
                for row in rows
            ],
        )
