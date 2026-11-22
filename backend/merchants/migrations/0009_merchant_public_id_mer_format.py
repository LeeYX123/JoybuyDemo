"""商家 public_id：UUID → MER+6 位数字（从 MER001000 起按 pk 升序回填）。

先加临时列再回填、删除旧列、重命名，避免 MySQL 把 char(32) 的 UUID 直接
改成 varchar(16) 时截断报错；SQLite/MySQL 都能安全执行。
"""

from django.db import migrations, models

MERCHANT_ID_START = 1000
MERCHANT_ID_DIGITS = 6


def backfill_public_ids(apps, schema_editor):
    Merchant = apps.get_model("merchants", "Merchant")
    for index, pk in enumerate(Merchant.objects.order_by("pk").values_list("pk", flat=True)):
        Merchant.objects.filter(pk=pk).update(
            public_id_new=f"MER{MERCHANT_ID_START + index:0{MERCHANT_ID_DIGITS}d}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("merchants", "0008_merchantapplication_shop_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="public_id_new",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.RunPython(backfill_public_ids, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="merchant",
            name="public_id",
        ),
        migrations.RenameField(
            model_name="merchant",
            old_name="public_id_new",
            new_name="public_id",
        ),
        migrations.AlterField(
            model_name="merchant",
            name="public_id",
            field=models.CharField(editable=False, max_length=16, unique=True),
        ),
    ]
