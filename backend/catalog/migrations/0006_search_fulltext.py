from django.db import connection, migrations

FULLTEXT_COLUMNS = ("title", "brand_name")


def create_fulltext_index(apps, schema_editor):
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        for column in FULLTEXT_COLUMNS:
            cursor.execute(
                f"ALTER TABLE product_search_document "
                f"ADD FULLTEXT INDEX psd_{column}_fulltext ({column})"
            )


def drop_fulltext_index(apps, schema_editor):
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        for column in FULLTEXT_COLUMNS:
            cursor.execute(f"ALTER TABLE product_search_document DROP INDEX psd_{column}_fulltext")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_productsearchdocument"),
    ]

    operations = [
        migrations.RunPython(create_fulltext_index, drop_fulltext_index),
    ]
