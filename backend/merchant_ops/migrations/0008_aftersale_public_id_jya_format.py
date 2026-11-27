"""售后 public_id：UUID → JYA + YYYYMMDD + 6 位随机（2026-11-27 阶段 1）。

做法同 accounts_buyers/0009：临时列 → 分批回填 → 删旧列 → rename → 唯一约束。
售后编号只用于对外展示/详情 URL，没有其它表把它当外键或快照，因此无需重写引用。
"""

from django.db import migrations, models

import common.id_migration as idmigration
import common.ids


def backfill(apps, schema_editor):
    idmigration.backfill_public_id(
        apps,
        schema_editor,
        app_label="merchant_ops",
        model_name="AfterSale",
        kind="after_sale",
    )
    idmigration.verify_public_ids(
        schema_editor,
        table="after_sale",
        field=idmigration.TEMP_FIELD,
        kind="after_sale",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("merchant_ops", "0007_merchantchatthread_inbound_window_count_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="aftersale",
            name="public_id_new",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(backfill, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(model_name="aftersale", name="public_id"),
        migrations.RenameField(
            model_name="aftersale",
            old_name="public_id_new",
            new_name="public_id",
        ),
        migrations.AlterField(
            model_name="aftersale",
            name="public_id",
            field=models.CharField(
                default=common.ids.new_after_sale_public_id,
                editable=False,
                max_length=32,
                unique=True,
            ),
        ),
    ]
