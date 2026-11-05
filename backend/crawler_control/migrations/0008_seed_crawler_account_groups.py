"""Backfill account groups from the existing free-text values.

Before 2026-11-05 ``account_group`` was a plain string on each account, so
the group list can only be derived from what accounts already carry. This
migration materialises those values (plus the ``default`` group) so the new
dropdown is never empty on an existing install.
"""

from django.db import migrations


def seed_groups(apps, schema_editor):
    group_model = apps.get_model("crawler_control", "CrawlerAccountGroup")
    account_model = apps.get_model("crawler_control", "CrawlerAccount")
    names = {
        (name or "").strip()
        for name in account_model.objects.values_list("account_group", flat=True)
    }
    names.add("default")
    for name in sorted(name for name in names if name):
        group_model.objects.get_or_create(name=name)


def drop_groups(apps, schema_editor):
    group_model = apps.get_model("crawler_control", "CrawlerAccountGroup")
    group_model.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crawler_control", "0007_crawler_account_groups_and_soft_delete"),
    ]

    operations = [
        migrations.RunPython(seed_groups, drop_groups),
    ]
