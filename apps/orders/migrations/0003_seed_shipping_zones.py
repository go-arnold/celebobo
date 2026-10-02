from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

ZONES = (
    {
        "name": "Kinshasa",
        "cities": ["Kinshasa"],
        "fee": Decimal("2.98"),
        "free_threshold": Decimal("199.00"),
        "delivery_estimate": "24 à 48 h",
        "is_default": False,
        "position": 1,
    },
    {
        "name": "Autres villes",
        "cities": [],
        "fee": Decimal("7.50"),
        "free_threshold": None,
        "delivery_estimate": "3 à 7 jours",
        "is_default": True,
        "position": 2,
    },
)


def seed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    zones = apps.get_model("orders", "ShippingZone")
    if not zones.objects.exists():
        zones.objects.bulk_create([zones(**zone) for zone in ZONES])


def unseed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    apps.get_model("orders", "ShippingZone").objects.filter(
        name__in=[zone["name"] for zone in ZONES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_coupons_and_shipping_zones")]

    operations = [migrations.RunPython(seed, unseed)]
