"""定时清扫：订单进度自动扭转 + 商家自动封店 + 过期未支付订单取消。

WP-42。开发环境没有 celery/beat，本命令是调度入口：
- 商家看板、管理端商家订单列表的 GET 会惰性调用同一组服务（保证演示及时）；
- 生产环境建议 cron 周期执行本命令（如每 10 分钟），见 docs/08 WP-42。
"""

from django.core.management.base import BaseCommand

from merchant_ops.services import auto_advance_progress
from merchants.services import auto_suspend_overdue_merchants
from orders.order_services import cancel_expired_orders


class Command(BaseCommand):
    help = "订单进度自动扭转 + 未处理订单自动封店 + 过期未支付订单取消"

    def handle(self, *args, **options):
        progress = auto_advance_progress()
        suspended = auto_suspend_overdue_merchants()
        canceled = cancel_expired_orders()
        self.stdout.write(
            self.style.SUCCESS(
                "进度推进 {advanced} 单、自动确认收货 {confirmed} 单、"
                "自动封店 {merchants} 家（{names}）、取消过期订单 {canceled} 单".format(
                    advanced=progress["advanced"],
                    confirmed=progress["confirmed"],
                    merchants=len(suspended),
                    names="、".join(m.display_name for m in suspended) or "无",
                    canceled=canceled.get("canceled", 0),
                )
            )
        )
