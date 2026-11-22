from django.db import migrations, models


# separate from 0005: the index cannot be built in the transaction that normalised the numbers
class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_phone_number_e164")]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("phone_number__isnull", False), models.Q(("phone_number", ""), _negated=True)),
                fields=("phone_number",),
                name="accounts_user_phone_unique",
            ),
        ),
    ]
