from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# Celebobo Plus members ship for free in the two home cities
MEMBER_ZONES = ("Bukavu", "Goma")


def mark_member_zones(apps: Apps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    zones = apps.get_model("orders", "ShippingZone").objects
    zones.filter(name__in=MEMBER_ZONES).update(member_free_shipping=True)


class Migration(migrations.Migration):
    dependencies = [("orders", "0005_deals")]

    operations = [
        migrations.AddField(
            model_name="shippingzone",
            name="member_free_shipping",
            field=models.BooleanField(default=False, verbose_name="livraison offerte aux abonnés"),
        ),
        migrations.RunPython(mark_member_zones, migrations.RunPython.noop),
    ]
