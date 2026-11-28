"""商家端 M01 经营看板与 M02 店铺管理。"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from catalog.models import Spu
from merchant_ops.api_utils import iso, money_str
from merchant_ops.merchant_context import (
    MerchantAPIView,
    memberships_for,
    merchant_payload,
    merchant_permission_codes,
)
from merchant_ops.models import AfterSale
from merchants.services import update_merchant_profile
from notifications.models import MerchantNotification
from orders.models import MerchantOrder, Order


def _day_bounds(days: int):
    today = timezone.localtime().date()
    start = today - timedelta(days=days - 1)
    start_dt = timezone.make_aware(timezone.datetime.combine(start, timezone.datetime.min.time()))
    return start, start_dt


def _order_bars(merchant, start) -> list:
    """按天聚合已付款商家子单数量（文档 M01 §8：订单数量柱状图）。"""

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


def _daily_stat_series(merchant, start) -> list:
    """按天统计序列（曝光度趋势 / 关注增量），只含真实有动作的日期。"""

    from merchants.models import MerchantDailyStat

    rows = MerchantDailyStat.objects.filter(merchant=merchant, stat_date__gte=start).order_by(
        "stat_date"
    )
    return [
        {
            "date": row.stat_date.isoformat(),
            "exposure": row.exposure_delta,
            "followers": row.followers_delta,
            "orders": row.order_count,
        }
        for row in rows
    ]


def run_lazy_sweeps() -> None:
    """开发环境无调度器的兜底：读看板时顺手推进自动扭转与自动封店。

    生产环境应改为 cron 周期执行 ``manage.py run_order_sweeps``（见 docs/08 WP-42），
    这里的读路径触发只是保证演示数据及时，不承担正式调度职责。
    """

    from merchant_ops.services import auto_advance_progress
    from merchants.services import auto_suspend_overdue_merchants

    try:
        auto_advance_progress()
        auto_suspend_overdue_merchants()
    except Exception:  # pragma: no cover - 清扫失败不阻塞看板读取
        pass


class MerchantOverviewView(MerchantAPIView):
    permission_any = ("merchant.dashboard.view",)

    def get(self, request):
        merchant = request.merchant
        today = timezone.localtime().date()
        range_param = (request.query_params.get("range") or "week").lower()
        days = 30 if range_param == "month" else 7
        start, start_dt = _day_bounds(days)

        # 惰性清扫：进看板先推进到期节点 / 自动封店（见 run_lazy_sweeps 注释）。
        run_lazy_sweeps()

        # 今日订单数量 = 【购买】成功（已付款）才算，加购不计入（文档 M01 §2）。
        today_orders = MerchantOrder.objects.filter(
            merchant=merchant,
            created_at__date=today,
            order__status=Order.Status.PAID,
        ).count()
        pending = MerchantOrder.objects.filter(
            merchant=merchant, status=MerchantOrder.Status.PENDING
        ).exclude(
            # 2026-11-29：父单已取消（Order.status=CANCELED）的子单不再是「待发货」，
            # 与商家订单列表 `views_merchant_orders._visible_orders` 同口径。
            order__status=Order.Status.CANCELED
        )
        pending_count = pending.count()
        # 迭代02：待发货金额 = 待处理订单的成本价合计（与管理端商家列表一致）。
        pending_amount = pending.aggregate(total=Sum("cost_total"))["total"] or 0

        pending_aftersales = AfterSale.objects.filter(
            merchant=merchant,
            state__in=[AfterSale.State.PENDING, AfterSale.State.PROCESSING],
        ).count()

        shipped_today = MerchantOrder.objects.filter(merchant=merchant, shipped_at__date=today)
        profit_today = sum((order.items_total - order.cost_total) for order in shipped_today)

        # 订单品类占比饼图：按已付款订单量统计，不按金额（文档 M01 §8 拍板 9）。
        category_share = list(
            MerchantOrder.objects.filter(merchant=merchant, order__status=Order.Status.PAID)
            .values("items__offer__sku__spu__merchant_category")
            .annotate(count=Count("id"))
            .order_by("-count")[:6]
        )

        notifications = list(
            MerchantNotification.objects.filter(merchant=merchant).order_by("-created_at")[:3]
        )

        return Response(
            {
                "merchant": merchant_payload(merchant, request.membership),
                "stats": {
                    "today_order_count": today_orders,
                    "pending_shipment_count": pending_count,
                    "pending_order_amount": money_str(pending_amount),
                    # 今日曝光度 = 当日累计新增，每天自动清零（文档 M01 §4）。
                    "today_exposure": merchant.exposure_delta
                    if merchant.exposure_day == today
                    else 0,
                    "follower_total": merchant.followers,
                    "follower_delta": merchant.follow_delta if merchant.follow_day == today else 0,
                    "credit_score": str(merchant.credit_score),
                    "store_status": merchant.onboarding_status,
                    "pending_after_sales": pending_aftersales,
                    "shipping_profit_today": money_str(profit_today),
                    "wallet_balance": money_str(merchant.wallet_balance),
                },
                "charts": {
                    "range": "week" if days == 7 else "month",
                    "order_bars": _order_bars(merchant, start),
                    "exposure_trend": _daily_stat_series(merchant, start),
                    "category_share": [
                        {
                            "category": Spu.merchant_category_label(
                                row["items__offer__sku__spu__merchant_category"] or ""
                            ),
                            "count": row["count"],
                        }
                        for row in category_share
                    ],
                },
                "notifications": [
                    {
                        "id": str(notification.public_id),
                        "kind": notification.kind,
                        "title": notification.title,
                        "content": notification.content,
                        "created_at": iso(notification.created_at),
                    }
                    for notification in notifications
                ],
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
