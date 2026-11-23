from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.cagnotte.domain.rules import CampaignKind, Payout, RewardStatus

KIND_CHOICES = [(item.value, item.label) for item in CampaignKind]
PAYOUT_CHOICES = [(item.value, item.value) for item in Payout]
STATUS_CHOICES = [(item.value, item.value) for item in RewardStatus]


class Campaign(models.Model):
    """A Cagnotte operation: one at a time, its conditions fixed once it starts."""

    name = models.CharField("nom", max_length=120)
    description = models.TextField("conditions", blank=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    # on the products concerned
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # most an order can get
    cap = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payout = models.CharField(max_length=14, choices=PAYOUT_CHOICES, default=Payout.POINTS.value)
    points_valid_days = models.PositiveSmallIntegerField(default=90)
    # none of either: every product
    categories = models.ManyToManyField("catalog.Category", blank=True, related_name="+")
    products = models.ManyToManyField("catalog.Product", blank=True, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "opération Cagnotte"
        verbose_name_plural = "opérations Cagnotte"
        ordering = ("-starts_at", "-pk")
        constraints = (
            models.CheckConstraint(
                condition=models.Q(percent__gt=0), name="cagnotte_campaign_percent"
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="cagnotte_campaign_period",
            ),
        )

    def __str__(self) -> str:
        return self.name


class Reward(models.Model):
    """What a delivered order earned from a Cagnotte operation (cashback or boosted points)."""

    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, related_name="rewards")
    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, related_name="cagnotte_reward"
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cagnotte_rewards"
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    payout = models.CharField(max_length=14, choices=PAYOUT_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    kept = models.DecimalField(max_digits=10, decimal_places=2)
    owed_back = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(0))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    # the end of the trial: then spendable (points) or due (Mobile Money)
    available_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reference = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "avantage Cagnotte"
        verbose_name_plural = "avantages Cagnotte"
        ordering = ("available_at", "pk")
        indexes = (models.Index(fields=("status", "available_at"), name="cagnotte_reward_due"),)

    def __str__(self) -> str:
        return f"{self.order_id} {self.amount}"
