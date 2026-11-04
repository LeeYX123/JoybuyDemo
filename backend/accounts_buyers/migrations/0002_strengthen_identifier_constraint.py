from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts_buyers", "0001_initial")]

    operations = [
        migrations.RemoveConstraint(
            model_name="buyeraccount",
            name="buyer_account_has_identifier",
        ),
        migrations.AddConstraint(
            model_name="buyeraccount",
            constraint=models.CheckConstraint(
                condition=(models.Q(email__isnull=False) & ~models.Q(email=""))
                | (models.Q(phone_e164__isnull=False) & ~models.Q(phone_e164="")),
                name="buyer_account_has_identifier",
            ),
        ),
    ]
