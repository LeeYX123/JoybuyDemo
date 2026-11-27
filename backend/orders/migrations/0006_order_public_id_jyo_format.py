"""订单 / 商家子单 public_id：UUID → JYO + YYYYMMDD + 6 位随机（2026-11-27 阶段 1）。

商家子单与平台订单同属订单体系，前缀格式一致（JYO）。

做法同 accounts_buyers/0009：临时列 → 分批回填 → 删旧列 → rename → 唯一约束。
订单号只出现在对外 URL / 展示字段，以及历史文本（钱包流水 note、幂等键、
通知正文）里；历史文本按「审计不可篡改」原则不重写，所以这里不更新它们。
"""

from django.db import migrations, models

import common.id_migration as idmigration
import common.ids


def backfill_orders(apps, schema_editor):
    idmigration.backfill_public_id(
        apps,
        schema_editor,
        app_label="orders",
        model_name="Order",
        kind="order",
    )
    idmigration.verify_public_ids(
        schema_editor,
        table="order",
        field=idmigration.TEMP_FIELD,
        kind="order",
    )


def backfill_merchant_orders(apps, schema_editor):
    idmigration.backfill_public_id(
        apps,
        schema_editor,
        app_label="orders",
        model_name="MerchantOrder",
        kind="order",
    )
    idmigration.verify_public_ids(
        schema_editor,
        table="merchant_order",
        field=idmigration.TEMP_FIELD,
        kind="order",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_autoordertask"),
    ]

    operations = [
        # 平台订单
        migrations.AddField(
            model_name="order",
            name="public_id_new",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(backfill_orders, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(model_name="order", name="public_id"),
        migrations.RenameField(model_name="order", old_name="public_id_new", new_name="public_id"),
        migrations.AlterField(
            model_name="order",
            name="public_id",
            field=models.CharField(
                default=common.ids.new_order_public_id,
                editable=False,
                max_length=32,
                unique=True,
            ),
        ),
        # 商家子单
        migrations.AddField(
            model_name="merchantorder",
            name="public_id_new",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(backfill_merchant_orders, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(model_name="merchantorder", name="public_id"),
        migrations.RenameField(
            model_name="merchantorder",
            old_name="public_id_new",
            new_name="public_id",
        ),
        migrations.AlterField(
            model_name="merchantorder",
            name="public_id",
            field=models.CharField(
                default=common.ids.new_order_public_id,
                editable=False,
                max_length=32,
                unique=True,
            ),
        ),
    ]
