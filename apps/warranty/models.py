from django.conf import settings
from django.db import models

from apps.warranty.domain.rules import ClaimKind, ClaimStatus, Outcome, Protection, ReturnMethod

DIGITS, PLACES = 10, 2

KIND_CHOICES = [(item.value, item.label) for item in ClaimKind]
PROTECTION_CHOICES = [(item.value, item.value) for item in Protection]
STATUS_CHOICES = [(item.value, item.value) for item in ClaimStatus]
OUTCOME_CHOICES = [(item.value, item.value) for item in Outcome]
METHOD_CHOICES = [(item.value, item.value) for item in ReturnMethod]
OPEN = [ClaimStatus.SUBMITTED, ClaimStatus.ANSWERED, ClaimStatus.RECEIVED, ClaimStatus.REPAIRING]


class Claim(models.Model):
    """A claim on one unit of an order line (warranty policy, "Comment faire une réclamation")."""

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="claims")
    item = models.ForeignKey("orders.OrderItem", on_delete=models.PROTECT, related_name="claims")
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="claims"
    )
    serial = models.CharField("numéro de série ou IMEI", max_length=40, blank=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    protection = models.CharField(max_length=16, choices=PROTECTION_CHOICES)
    description = models.TextField()
    photos = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=ClaimStatus.SUBMITTED.value, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    answer_due = models.DateTimeField()
    # step 2: how the product comes back
    return_method = models.CharField(max_length=10, choices=METHOD_CHOICES, blank=True)
    answer_note = models.TextField(blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    # step 3: the product is in (the drop-off slip is the claim number and this date)
    received_at = models.DateTimeField(null=True, blank=True)
    sealed = models.BooleanField(null=True, blank=True)
    diagnosis_due = models.DateTimeField(null=True, blank=True)
    # step 4: diagnosis and outcome
    covered = models.BooleanField(null=True, blank=True)
    outcome = models.CharField(max_length=12, choices=OUTCOME_CHOICES, blank=True)
    diagnosis_note = models.TextField(blank=True)
    diagnosed_at = models.DateTimeField(null=True, blank=True)
    outcome_due = models.DateTimeField(null=True, blank=True)
    new_serial = models.CharField(max_length=40, blank=True)
    quote = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES, null=True, blank=True)
    exchange_warranty_until = models.DateField(null=True, blank=True)
    repaired_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "réclamation"
        verbose_name_plural = "réclamations"
        constraints = (
            # one claim at a time per line
            models.UniqueConstraint(
                fields=("item",),
                condition=models.Q(status__in=OPEN),
                name="warranty_one_open_claim_per_line",
            ),
        )

    def __str__(self) -> str:
        return self.number

    @property
    def number(self) -> str:
        return f"RC-{self.pk:05d}"
