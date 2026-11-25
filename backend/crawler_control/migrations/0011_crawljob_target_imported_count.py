from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crawler_control", "0010_crawljob_allow_pagination"),
    ]

    operations = [
        migrations.AddField(
            model_name="crawljob",
            name="target_imported_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
