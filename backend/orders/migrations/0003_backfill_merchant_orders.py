"""为历史订单补齐商家履约子单。

升级前 ``order`` 只有买家侧一张表，商家端无法按店隔离。这里按
「父单 × 商家」把已有订单项聚合成 ``MerchantOrder``，并回填
``OrderItem.merchant_order``；代价快照缺失时取 0（历史订单本就没有成本）。
"""

from decimal import Decimal

from django.db import migrations


def backfill(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    MerchantOrder = apps.get_model("orders", "MerchantOrder")
    Offer = apps.get_model("offers", "Offer")

    offer_merchants = dict(Offer.objects.values_list("pk", "merchant_id"))

    for order in Order.objects.iterator():
        items = list(OrderItem.objects.filter(order=order, merchant_order__isnull=True))
        if not items:
            continue
        buckets = {}
        for item in items:
            merchant_id = offer_merchants.get(item.offer_id)
            if merchant_id is None:
                continue
            buckets.setdefault(merchant_id, []).append(item)

        for merchant_id, merchant_items in buckets.items():
            items_total = sum(
                (item.unit_price or Decimal("0")) * item.quantity for item in merchant_items
            )
            cost_total = sum(
                (item.unit_cost or Decimal("0")) * item.quantity for item in merchant_items
            )
            merchant_order = MerchantOrder.objects.create(
                order=order,
                merchant_id=merchant_id,
                currency=order.currency.code,
                items_total=items_total,
                cost_total=cost_total,
                status="PENDING",
                progress=-1,
                node_times=[],
                payment_method="",
                recipient_region=(order.shipping_address or {}).get("region", ""),
            )
            OrderItem.objects.filter(pk__in=[item.pk for item in merchant_items]).update(
                merchant_order=merchant_order
            )


def unbackfill(apps, schema_editor):
    MerchantOrder = apps.get_model("orders", "MerchantOrder")
    MerchantOrder.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_orderitem_unit_cost_merchantorder_and_more")]

    operations = [migrations.RunPython(backfill, unbackfill)]
