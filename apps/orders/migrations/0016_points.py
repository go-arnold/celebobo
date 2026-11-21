from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    """What an order paid with fidelity points (formerly cashback); data is kept.

    The checks naming the column are dropped before the rename and added back after,
    so the migration also unapplies cleanly.
    """

    dependencies = [
        ("catalog", "0007_category_parent"),
        ("orders", "0015_delivery_attempts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="order", name="orders_order_total_consistent"),
        migrations.RemoveConstraint(model_name="orderitem", name="orders_item_amounts_positive"),
        migrations.RemoveConstraint(model_name="orderitem", name="orders_item_paid_consistent"),
        migrations.RenameField("order", "cashback", "points"),
        migrations.RenameField("orderitem", "cashback", "points"),
        migrations.RenameField("orderlinereturn", "cashback", "points"),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("discount") - F("points") + F("shipping_fee")),
                name="orders_order_total_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=Q(amount_paid__gte=0, discount__gte=0, points__gte=0),
                name="orders_item_amounts_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=Q(
                    amount_paid=F("unit_price") * F("quantity") - F("discount") - F("points")
                ),
                name="orders_item_paid_consistent",
            ),
        ),
    ]
