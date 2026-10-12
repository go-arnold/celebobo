from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.utils.text import slugify

# a brand is created only when an existing product name matches one of its words
BRANDS = (
    ("Samsung", ("samsung", "galaxy")),
    ("Apple", ("apple", "iphone", "ipad", "macbook", "airpods")),
    ("Xiaomi", ("xiaomi", "redmi", "poco")),
    ("Tecno", ("tecno",)),
    ("Infinix", ("infinix",)),
    ("Itel", ("itel",)),
    ("Huawei", ("huawei",)),
    ("Oppo", ("oppo",)),
    ("Nokia", ("nokia",)),
    ("Lenovo", ("lenovo",)),
    ("HP", ("hp",)),
    ("Dell", ("dell",)),
    ("JBL", ("jbl",)),
    ("Sony", ("sony", "playstation")),
    ("Anker", ("anker",)),
    ("Baseus", ("baseus",)),
    ("Microsoft", ("microsoft", "xbox")),
    ("Nintendo", ("nintendo",)),
)


def backfill(apps: Apps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    brand_model = apps.get_model("catalog", "Brand")
    products = apps.get_model("catalog", "Product")._base_manager.filter(brand__isnull=True)
    position = 0
    for name, words in BRANDS:
        pattern = r"\y(" + "|".join(words) + r")\y"
        ids = list(products.filter(name__iregex=pattern).values_list("pk", flat=True))
        if not ids:
            continue
        position += 1
        brand, _ = brand_model.objects.get_or_create(
            slug=slugify(name), defaults={"name": name, "is_featured": True, "position": position}
        )
        products.filter(pk__in=ids).update(brand=brand)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_brands")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
