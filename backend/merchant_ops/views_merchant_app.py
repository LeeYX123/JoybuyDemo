"""商家端 M01 经营看板与 M02 店铺管理。"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from merchant_ops.api_utils import iso, money_str
from merchant_ops.merchant_context import (
    MerchantAPIView,
    memberships_for,
    merchant_payload,
    merchant_permission_codes,
)
from merchant_ops.models import AfterSale
from merchants.services import update_merchant_profile
from orders.models import MerchantOrder


def _day_bounds(days: int):
    today = timezone.localtime().date()
    start = today - timedelta(days=days - 1)
    start_dt = timezone.make_aware(timezone.datetime.combine(start, timezone.datetime.min.time()))
    return start, start_dt


def _order_bars(merchant, start) -> list:
    """按天聚合下单数量。

    曝光目前只有商家级累计值（``merchant.exposure``），没有按天的明细表，
    所以这里**不伪造**曝光柱状图——等后端补日汇总再返回，避免前端展示假数据。
    """

    rows = (
        MerchantOrder.objects.filter(merchant=merchant, created_at__date__gte=start)
        .extra(select={"day": "DATE(created_at)"})
        .values("day")
        .annotate(count=Count("id"))
    )
    counts = {str(row["day"]): row["count"] for row in rows}
    today = timezone.localtime().date()
    series = []
    cursor = start
    while cursor <= today:
        series.append({"date": cursor.isoformat(), "count": counts.get(cursor.isoformat(), 0)})
        cursor += timedelta(days=1)
    return series


class MerchantOverviewView(MerchantAPIView):
    permission_any = ("merchant.dashboard.view",)

    def get(self, request):
        merchant = request.merchant
        today = timezone.localtime().date()
        start, start_dt = _day_bounds(7)

        today_orders = MerchantOrder.objects.filter(
            merchant=merchant, created_at__date=today
        ).count()
        pending = MerchantOrder.objects.filter(
            merchant=merchant, status=MerchantOrder.Status.PENDING
        )
        pending_count = pending.count()
        pending_amount = pending.aggregate(total=Sum("items_total"))["total"] or 0

        pending_aftersales = AfterSale.objects.filter(
            merchant=merchant,
            state__in=[AfterSale.State.PENDING, AfterSale.State.PROCESSING],
        ).count()

        shipped_today = MerchantOrder.objects.filter(merchant=merchant, shipped_at__date=today)
        profit_today = sum((order.items_total - order.cost_total) for order in shipped_today)

        category_share = list(
            MerchantOrder.objects.filter(merchant=merchant)
            .values("items__offer__sku__spu__local_category__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        return Response(
            {
                "merchant": merchant_payload(merchant, request.membership),
                "stats": {
                    "today_order_count": today_orders,
                    "pending_shipment_count": pending_count,
                    "pending_order_amount": money_str(pending_amount),
                    "today_exposure": merchant.exposure,
                    "follower_total": merchant.followers,
                    "follower_delta": merchant.follow_delta if merchant.follow_day == today else 0,
                    "credit_score": str(merchant.credit_score),
                    "store_status": merchant.onboarding_status,
                    "pending_after_sales": pending_aftersales,
                    "shipping_profit_today": money_str(profit_today),
                    "wallet_balance": money_str(merchant.wallet_balance),
                },
                "charts": {
                    "range": "week",
                    "order_bars": _order_bars(merchant, start),
                    "category_share": [
                        {
                            "category": row["items__offer__sku__spu__local_category__name"]
                            or "未分类",
                            "count": row["count"],
                        }
                        for row in category_share
                    ],
                },
                "permissions": sorted(merchant_permission_codes(request.membership)),
            }
        )


class MerchantProfileView(MerchantAPIView):
    permission_any = ("merchant.store.manage",)

    def get(self, request):
        merchant = request.merchant
        payload = merchant_payload(merchant, request.membership)
        payload.update(
            {
                "wallet_balance": money_str(merchant.wallet_balance),
                "deposit_balance": money_str(merchant.deposit_balance),
                "deposit_required": money_str(merchant.deposit_required)
                if merchant.deposit_required is not None
                else None,
                "followers": merchant.followers,
                "exposure": merchant.exposure,
                "ban_after_days": merchant.ban_after_days,
                "referral_code": merchant.referral_code,
                "joined": iso(merchant.created_at),
            }
        )
        return Response({"merchant": payload})

    def patch(self, request):
        merchant = request.merchant
        payload = request.data or {}
        merchant = update_merchant_profile(
            merchant,
            display_name=payload.get("name"),
            avatar_url=payload.get("avatar"),
        )
        return Response({"merchant": merchant_payload(merchant, request.membership)})


class MerchantShopsView(MerchantAPIView):
    """切换店铺用的可选店铺列表（不吃店铺上下文）。"""

    skip_context = True

    def get(self, request):
        staff = getattr(request, "staff_account", None)
        if staff is None:
            raise StaffApiError(
                business_code="MERCHANT_AUTH_REQUIRED",
                message="请先登录商家账号。",
                status_code=401,
            )
        rows = []
        for membership in memberships_for(staff):
            payload = merchant_payload(membership.merchant, membership)
            payload["permissions"] = sorted(merchant_permission_codes(membership))
            rows.append(payload)
        return Response({"items": rows})
