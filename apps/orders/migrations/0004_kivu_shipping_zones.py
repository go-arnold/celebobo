from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# Bukavu and Goma first, then their surroundings, then the rest of the country.
# Fees and delays are provisional: the team edits them in the back-office.
CORE = {"fee": Decimal("2.98"), "free_threshold": Decimal("199.00"), "delivery_estimate": "24 à 48 h"}
ZONES = (
    {"name": "Bukavu", "cities": ["Bukavu"], **CORE, "is_default": False, "position": 1},
    {"name": "Goma", "cities": ["Goma"], **CORE, "is_default": False, "position": 2},
    {
        "name": "Environs de Bukavu et Goma",
        "cities": [
            "Kabare",
            "Kavumu",
            "Walungu",
            "Kalehe",
            "Uvira",
            "Sake",
            "Minova",
            "Kibumba",
            "Rutshuru",
        ],
        "fee": Decimal("5.00"),
        "free_threshold": None,
        "delivery_estimate": "2 à 4 jours",
        "is_default": False,
        "position": 3,
    },
    {
        "name": "Reste du pays",
        "cities": [],
        "fee": Decimal("7.50"),
        "free_threshold": None,
        "delivery_estimate": "3 à 7 jours",
        "is_default": True,
        "position": 4,
    },
)
FIRST_SEED = {
    "Kinshasa": {"cities": ["Kinshasa"], "fee": Decimal("2.98")},
    "Autres villes": {"cities": [], "fee": Decimal("7.50")},
}


def _untouched(zones: object) -> bool:
    current = {zone.name: zone for zone in zones.objects.all()}  # type: ignore[attr-defined]
    return set(current) == set(FIRST_SEED) and all(
        current[name].cities == values["cities"] and current[name].fee == values["fee"]
        for name, values in FIRST_SEED.items()
    )


def relocate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    zones = apps.get_model("orders", "ShippingZone")
    if zones.objects.exists() and not _untouched(zones):
        return
    zones.objects.all().delete()
    zones.objects.bulk_create([zones(**zone) for zone in ZONES])


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_seed_shipping_zones")]

    operations = [migrations.RunPython(relocate, migrations.RunPython.noop)]
