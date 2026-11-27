"""阶段 2 存量回填迁移：为历史已支付订单 / 已填运单号的子单补记录。

新建三张表（payment / refund / shipment）后按 ``orders/id_backfill.py`` 的规则
回填；退款因售后单没有金额字段跳过（不造 0 元假退款）。迁移内部做行数 /
去重 / 格式校验，不一致直接失败。
"""

from django.db import migrations

import orders.id_backfill as idbackfill


def forwards(apps, schema_editor):  # noqa: ARG001 - Django 迁移签名
    idbackfill.backfill_all(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_payment_refund_shipment"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
