from django.conf import settings
from django.db import models

from apps.cash.domain.rules import Level
from apps.standing.domain.rules import SanctionKind, SanctionStatus

LEVEL_CHOICES = [(item.value, item.label) for item in Level]
KIND_CHOICES = [(item.value, item.label) for item in SanctionKind]
STATUS_CHOICES = [(item.value, item.value) for item in SanctionStatus]


class ResellerLevel(models.Model):
    """A reseller's level since the last quarterly review (reseller policy, section 9)."""

    reseller = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reseller_level"
    )
    level = models.CharField(max_length=12, choices=LEVEL_CHOICES, default=Level.BEGINNER.value)
    # what the review saw: validated sales of the last 3 months and the rating
    sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "niveau de revendeur"
        verbose_name_plural = "niveaux de revendeurs"

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.level}"


class Sanction(models.Model):
    """A sanction (reseller policy, section 10): a warning applies at once; a suspension or an
    exclusion is first notified and the reseller may explain within 48 hours, unless urgent."""

    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sanctions"
    )
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    reason = models.TextField()
    urgent = models.BooleanField(default=False)
    days = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    explain_until = models.DateTimeField(null=True, blank=True)
    explanation = models.TextField(blank=True)
    explained_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "sanction"
        verbose_name_plural = "sanctions"

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.kind} {self.status}"
