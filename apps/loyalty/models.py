from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.loyalty.domain.points import EntryKind

SETTINGS_ID = 1
ENTRY_KIND_CHOICES = [(item.value, item.value) for item in EntryKind]
MONEY_DIGITS = 10
MONEY_PLACES = 2


# every rule of the programmes is set here by an admin; a programme stays hidden until enabled
class LoyaltySettings(models.Model):
    points_enabled = models.BooleanField("points de fidélité actifs", default=False)
    # points earned on what the client really paid for the items (1 point = $1)
    points_percent = models.DecimalField(
        "points gagnés (%)", max_digits=5, decimal_places=2, default=Decimal("1.00")
    )
    # the whole balance stays valid while the client buys at least once in this many months
    points_validity_months = models.PositiveSmallIntegerField(default=12)
    # when the programme was switched off: clients keep using their points for 3 months
    points_disabled_at = models.DateTimeField(null=True, blank=True, editable=False)
    # referral points: share of an invited client's invoices, for this many months after joining
    referral_percent = models.DecimalField(
        "points de parrainage (%)", max_digits=5, decimal_places=2, default=Decimal("0.30")
    )
    referral_months = models.PositiveSmallIntegerField("durée du parrainage (mois)", default=12)
    app_store_url = models.URLField(max_length=300, blank=True)
    play_store_url = models.URLField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "paramètres de fidélité"
        verbose_name_plural = "paramètres de fidélité"

    def __str__(self) -> str:
        return "Paramètres de fidélité"


# credits (earn, refund) keep what is left to spend; debits are negative lines
class PointsEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="points_entries"
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=20, choices=ENTRY_KIND_CHOICES)
    amount = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    remaining = models.DecimalField(
        max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES, default=Decimal(0)
    )
    available_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mouvement de points"
        verbose_name_plural = "mouvements de points"
        ordering = ("created_at", "pk")
        indexes = (models.Index(fields=("user", "available_at"), name="loyalty_points_user"),)
        constraints = (
            # an order earns, spends and pays its referral once; reversals and refunds can come
            # in parts (line returns), bounded by what was earned and spent
            models.UniqueConstraint(
                fields=("order", "kind"),
                condition=models.Q(order__isnull=False, kind__in=("earn", "spend", "referral")),
                name="loyalty_points_once_per_order",
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} {self.amount:+}"
