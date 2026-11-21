from django.db import migrations, models
from django.db.models import F


def attached_on_signup(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Clients invited before this field existed joined their reseller when they signed up."""
    User = apps.get_model("accounts", "User")
    User.objects.filter(invited_by__isnull=False, invited_at__isnull=True).update(
        invited_at=F("date_joined")
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="invited_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="invité le"),
        ),
        migrations.RunPython(attached_on_signup, migrations.RunPython.noop),
    ]
