from django.conf import settings
from django.db import models

DIGITS, PLACES = 10, 2


class CashCollection(models.Model):
    """The money a reseller collected for one order: due to Celebobo within 24 hours."""

    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_collections"
    )
    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, related_name="cash_collection"
    )
    order_number = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    # what remittances already cover of it (oldest collections first)
    covered = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES, default=0)
    collected_at = models.DateTimeField()
    due_at = models.DateTimeField(db_index=True)
    # the order was cancelled before any remittance: nothing is owed
    voided_at = models.DateTimeField(null=True, blank=True)
    # the reseller was told once that the 24 hours are over
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("due_at", "pk")
        verbose_name = "encaissement"
        verbose_name_plural = "encaissements"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(covered__gte=0, covered__lte=models.F("amount")),
                name="cash_collection_covered_within_amount",
            ),
        )

    def __str__(self) -> str:
        return f"{self.order_number} {self.amount}"


class CashRemittance(models.Model):
    """Money a reseller handed to Celebobo (Mobile Money), recorded by staff."""

    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_remittances"
    )
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    reference = models.CharField("référence Mobile Money", max_length=80, blank=True)
    received_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at", "-pk")
        verbose_name = "reversement"
        verbose_name_plural = "reversements"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="cash_remittance_amount_positive"
            ),
        )

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.amount}"
