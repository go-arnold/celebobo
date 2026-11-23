from django.conf import settings
from django.db import models

from apps.credit.domain.rules import EntryKind

DIGITS, PLACES = 10, 2
KIND_CHOICES = [(item.value, item.label) for item in EntryKind]


class CreditEntry(models.Model):
    """One movement of a client's store credit. Issued credit keeps what is left of it
    (`remaining`) and its expiry; a spending names the credit it was taken from (`source`), so a
    cancellation gives it back to the same credit, with the same expiry."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credit_entries"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    remaining = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES, default=0)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    source = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="uses"
    )
    # what is left to give back of a spending (a cancellation, a return)
    unreturned = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES, default=0)
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "mouvement d'avoir"
        verbose_name_plural = "mouvements d'avoir"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(remaining__gte=0, unreturned__gte=0),
                name="credit_entry_amounts_positive",
            ),
        )

    def __str__(self) -> str:
        return f"{self.kind} {self.amount}"
