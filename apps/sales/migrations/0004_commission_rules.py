# Commission rules decided on 16 Nov 2026: the per-reseller rate is gone. Each sale says whether
# it earns a commission (decided when it is recorded or converted) and each ledger entry says
# which rule set its amount. Entries written before keep `legacy_rate`.

from django.db import migrations, models

EARNED = "earned"


def flag_commissionable_sales(apps, schema_editor):  # type: ignore[no-untyped-def]
    # the old engine earned on every reseller sale: those that earned stay recomputable on edit
    Sale = apps.get_model("sales", "Sale")
    CommissionEntry = apps.get_model("sales", "CommissionEntry")
    earned = CommissionEntry.objects.filter(kind=EARNED, sale__isnull=False).values("sale_id")
    Sale.objects.filter(pk__in=earned).update(commissionable=True)


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0003_sale_origin"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="commissionable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="commissionentry",
            name="rule",
            field=models.CharField(
                choices=[
                    ("paid", "paid"),
                    ("margin", "margin"),
                    ("partner_gain", "partner_gain"),
                    ("unknown_cost", "unknown_cost"),
                    ("legacy_rate", "legacy_rate"),
                ],
                default="legacy_rate",
                max_length=16,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(flag_commissionable_sales, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="commissionentry",
            name="rate",
        ),
    ]
