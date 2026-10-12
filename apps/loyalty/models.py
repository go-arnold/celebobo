from decimal import Decimal

from django.db import models

SETTINGS_ID = 1
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
