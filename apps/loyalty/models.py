from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.loyalty.domain.cashback import EntryKind
from apps.loyalty.domain.membership import Plan, RequestStatus

SETTINGS_ID = 1
PLAN_CHOICES = [(item.value, item.value) for item in Plan]
REQUEST_STATUS_CHOICES = [(item.value, item.value) for item in RequestStatus]
ENTRY_KIND_CHOICES = [(item.value, item.value) for item in EntryKind]
MONEY_DIGITS = 10
MONEY_PLACES = 2


# every rule of the programmes is set here by an admin; a programme stays hidden until enabled
class LoyaltySettings(models.Model):
    membership_enabled = models.BooleanField("abonnement actif", default=False)
    membership_monthly_price = models.DecimalField(
        default=Decimal("4.99"), max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    membership_yearly_price = models.DecimalField(
        default=Decimal("49.00"), max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    membership_trial_days = models.PositiveSmallIntegerField(default=30)
    membership_reminder_days = models.PositiveSmallIntegerField(default=3)
    cashback_enabled = models.BooleanField("cagnotte active", default=False)
    cashback_members_only = models.BooleanField("cagnotte réservée aux abonnés", default=True)
    cashback_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("3.00"))
    cashback_max_share = models.PositiveSmallIntegerField(default=50)
    cashback_min_balance = models.DecimalField(
        default=Decimal("1.00"), max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    cashback_validity_months = models.PositiveSmallIntegerField(default=12)
    app_store_url = models.URLField(max_length=300, blank=True)
    play_store_url = models.URLField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "paramètres de fidélité"
        verbose_name_plural = "paramètres de fidélité"

    def __str__(self) -> str:
        return "Paramètres de fidélité"


class Membership(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership"
    )
    plan = models.CharField(max_length=8, choices=PLAN_CHOICES)
    ends_at = models.DateTimeField(db_index=True)
    trial_started_at = models.DateTimeField(null=True, blank=True)
    # digits of the phone used for the trial, so one number gets one trial
    trial_phone = models.CharField(max_length=20, blank=True, db_index=True)
    reminded_for = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "abonnement"
        verbose_name_plural = "abonnements"

    def __str__(self) -> str:
        return f"{self.user} jusqu'au {self.ends_at:%d/%m/%Y}"


class MembershipRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership_requests"
    )
    plan = models.CharField(max_length=8, choices=PLAN_CHOICES)
    price = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    payment_method = models.CharField(max_length=16)
    status = models.CharField(
        max_length=10,
        choices=REQUEST_STATUS_CHOICES,
        default=RequestStatus.PENDING.value,
        db_index=True,
    )
    note = models.CharField(max_length=255, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "demande d'abonnement"
        verbose_name_plural = "demandes d'abonnement"
        ordering = ("-created_at", "-pk")
        constraints = (
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(status="pending"),
                name="loyalty_one_pending_request",
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} — {self.plan}"


# credits (earn, refund) keep what is left to spend; debits are negative lines
class CashbackEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cashback_entries"
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=10, choices=ENTRY_KIND_CHOICES)
    amount = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    remaining = models.DecimalField(
        max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES, default=Decimal(0)
    )
    available_at = models.DateTimeField(db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mouvement de cagnotte"
        verbose_name_plural = "mouvements de cagnotte"
        ordering = ("created_at", "pk")
        indexes = (models.Index(fields=("user", "available_at"), name="loyalty_cashback_user"),)
        constraints = (
            models.UniqueConstraint(
                fields=("order", "kind"),
                condition=models.Q(order__isnull=False) & ~models.Q(kind="expiry"),
                name="loyalty_cashback_once_per_order",
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} {self.amount:+}"
