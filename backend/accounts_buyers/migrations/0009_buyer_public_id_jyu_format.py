"""买家 public_id：UUID → JYU + 10 位随机（2026-11-27 全站编号改造阶段 1）。

MySQL 不能安全地把 char(32) 的编号列原地改类型/缩窄（merchants/0009 事故），
所以走「加临时列 → 分批回填 → 删旧列 → rename → 加唯一约束」。

回填顺序按 pk 升序；每批 500 行 executemany 更新并在内存校验不重号，最后
``COUNT(*) = COUNT(DISTINCT public_id)`` + 正则 + 无 32 位十六进制残留。
同一迁移顺带把 Crisp 线程键 ``bp:<buyer>`` / ``bm:<buyer>:<merchant>`` 的
买家段换成新号（商家段由 merchants 迁移负责；映射是双射，互不干扰）。
"""

from django.db import migrations, models

import common.id_migration as idmigration
import common.ids


def backfill(apps, schema_editor):
    mapping = idmigration.backfill_public_id(
        apps,
        schema_editor,
        app_label="accounts_buyers",
        model_name="BuyerAccount",
        kind="buyer",
    )
    idmigration.rewrite_thread_keys(schema_editor, mapping=mapping, mode="buyer")
    idmigration.verify_public_ids(
        schema_editor,
        table="buyer_account",
        field=idmigration.TEMP_FIELD,
        kind="buyer",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts_buyers", "0008_buyeridentity_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="buyeraccount",
            name="public_id_new",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(backfill, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(model_name="buyeraccount", name="public_id"),
        migrations.RenameField(
            model_name="buyeraccount",
            old_name="public_id_new",
            new_name="public_id",
        ),
        migrations.AlterField(
            model_name="buyeraccount",
            name="public_id",
            field=models.CharField(
                default=common.ids.new_buyer_public_id,
                editable=False,
                max_length=32,
                unique=True,
            ),
        ),
    ]
