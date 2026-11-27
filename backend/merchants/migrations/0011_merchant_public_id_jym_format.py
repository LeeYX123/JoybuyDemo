"""商家 public_id：MER+6 位顺序号 → JYM + 10 位随机（2026-11-27 阶段 1）。

删除原来「取 max+1 顺序编号 + select_for_update 锁号段」的逻辑，改统一生成器。
做法同 merchants/0009：临时列 → 分批回填 → 删旧列 → rename → 唯一约束。

同一迁移把 Crisp 线程键 ``merchant:<merchant>`` / ``bm:<buyer>:<merchant>`` 的
商家段换成新号（买家段已由 accounts_buyers/0009 处理）。
"""

from django.db import migrations, models

import common.id_migration as idmigration
import common.ids


def backfill(apps, schema_editor):
    mapping = idmigration.backfill_public_id(
        apps,
        schema_editor,
        app_label="merchants",
        model_name="Merchant",
        kind="merchant",
    )
    idmigration.rewrite_thread_keys(schema_editor, mapping=mapping, mode="merchant")
    idmigration.verify_public_ids(
        schema_editor,
        table="merchant",
        field=idmigration.TEMP_FIELD,
        kind="merchant",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("merchants", "0010_merchant_membership_staff_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="public_id_new",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(backfill, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(model_name="merchant", name="public_id"),
        migrations.RenameField(
            model_name="merchant",
            old_name="public_id_new",
            new_name="public_id",
        ),
        migrations.AlterField(
            model_name="merchant",
            name="public_id",
            field=models.CharField(
                default=common.ids.new_merchant_public_id,
                editable=False,
                max_length=32,
                unique=True,
            ),
        ),
    ]
