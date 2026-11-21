import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# entries written before validation existed were already counted as due: they stay validated
def validate_existing_entries(apps, schema_editor):  # type: ignore[no-untyped-def]
    entry = apps.get_model("sales", "CommissionEntry")
    entry.objects.filter(available_at__isnull=True).update(available_at=models.F("created_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
        ("sales", "0004_commission_rules"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PayoutStatement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("payout_date", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("prepared", "prepared"),
                            ("paid", "paid"),
                            ("cancelled", "cancelled"),
                        ],
                        default="prepared",
                        max_length=10,
                    ),
                ),
                ("commissions", models.DecimalField(decimal_places=2, max_digits=10)),
                ("delivery_fees", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total", models.DecimalField(decimal_places=2, max_digits=10)),
                ("prepared_at", models.DateTimeField()),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "payout",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="statement",
                        to="sales.payout",
                    ),
                ),
                (
                    "reseller",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payout_statements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "relevé de paiement",
                "verbose_name_plural": "relevés de paiement",
                "ordering": ("-payout_date", "-pk"),
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "cancelled"), _negated=True),
                        fields=("reseller", "payout_date"),
                        name="sales_statement_once_per_date",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="commissionentry",
            name="available_at",
            field=models.DateTimeField(db_index=True, null=True),
        ),
        migrations.RunPython(validate_existing_entries, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="commissionentry",
            name="available_at",
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddField(
            model_name="commissionentry",
            name="statement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="commission_entries",
                to="sales.payoutstatement",
            ),
        ),
        migrations.CreateModel(
            name="DeliveryCredit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("order_number", models.CharField(max_length=16)),
                (
                    "kind",
                    models.CharField(
                        choices=[("credit", "credit"), ("reversal", "reversal")], max_length=10
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("available_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="orders.order",
                    ),
                ),
                (
                    "reseller",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="delivery_credits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "statement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="delivery_credits",
                        to="sales.payoutstatement",
                    ),
                ),
            ],
            options={
                "verbose_name": "frais de livraison reversés",
                "verbose_name_plural": "frais de livraison reversés",
                "ordering": ("-created_at", "-pk"),
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("order__isnull", False)),
                        fields=("order", "kind"),
                        name="sales_delivery_credit_once_per_order",
                    )
                ],
            },
        ),
    ]
