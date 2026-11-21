from decimal import Decimal

from django.db import migrations


# the default rate becomes 1 % (the loyalty policy); a rate an admin already changed is kept
def one_percent(apps, schema_editor):  # type: ignore[no-untyped-def]
    settings = apps.get_model("loyalty", "LoyaltySettings")
    settings.objects.filter(points_percent=Decimal("3.00")).update(points_percent=Decimal("1.00"))


# points no longer expire one by one: the whole balance expires after a year without purchase
def no_dated_expiry(apps, schema_editor):  # type: ignore[no-untyped-def]
    apps.get_model("loyalty", "PointsEntry").objects.update(expires_at=None)


class Migration(migrations.Migration):
    """The cashback ("Cagnotte") ledger becomes the fidelity points ledger; data is kept."""

    dependencies = [
        ("loyalty", "0004_cashback_parts_per_order"),
        ("orders", "0015_delivery_attempts"),
    ]

    operations = [
        migrations.RenameModel("CashbackEntry", "PointsEntry"),
        migrations.RenameField("loyaltysettings", "cashback_enabled", "points_enabled"),
        migrations.RenameField("loyaltysettings", "cashback_percent", "points_percent"),
        migrations.RenameField(
            "loyaltysettings", "cashback_validity_months", "points_validity_months"
        ),
        migrations.RemoveField("loyaltysettings", "cashback_members_only"),
        migrations.RemoveField("loyaltysettings", "cashback_max_share"),
        migrations.RemoveField("loyaltysettings", "cashback_min_balance"),
        migrations.RunPython(one_percent, migrations.RunPython.noop),
        migrations.RunPython(no_dated_expiry, migrations.RunPython.noop),
    ]
