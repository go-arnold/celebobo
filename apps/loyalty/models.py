from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.loyalty.domain.cashback import EntryKind
from apps.loyalty.domain.rules import Trigger

SETTINGS_ID = 1
ENTRY_KIND_CHOICES = [(item.value, item.value) for item in EntryKind]
TRIGGER_CHOICES = [(item.value, item.value) for item in Trigger]
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


# dynamic loyalty rules set by the admin through the back office
class LoyaltyRule(models.Model):
    class Trigger(models.TextChoices):
        USER_REGISTERED = "user_registered", "Inscription"
        USER_LOGIN_DAILY = "user_login_daily", "Connexion quotidienne"
        NEWSLETTER_SUBSCRIBED = "newsletter_subscribed", "Abonnement newsletter"
        PROFILE_COMPLETED = "profile_completed", "Profil complété"
        FIRST_PURCHASE = "first_purchase", "Premier achat"
        PURCHASE_MADE = "purchase_made", "Achat effectué"
        ORDER_VALUE_MILESTONE = "order_value_milestone", "Seuil de montant de commande"
        PRODUCT_PURCHASED = "product_purchased", "Produit acheté"
        CATEGORY_PURCHASED = "category_purchased", "Catégorie achetée"
        REVIEW_CREATED = "review_created", "Avis produit déposé"
        FRIEND_REFERRED = "friend_referred", "Parrainage d'ami"
        SOCIAL_SHARED = "social_shared", "Partage sur réseau social"
        BIRTHDAY_REACHED = "birthday_reached", "Anniversaire"
        WINBACK_INACTIVITY = "winback_inactivity", "Retour après inactivité"

    name = models.CharField(max_length=150, verbose_name="nom de la règle")
    trigger = models.CharField(
        max_length=30, choices=Trigger.choices, db_index=True, verbose_name="déclencheur"
    )
    condition = models.JSONField(default=dict, blank=True, verbose_name="condition")
    action_type = models.CharField(
        max_length=20, default="add_points", verbose_name="type d'action"
    )
    points_value = models.IntegerField(verbose_name="points attribués")
    is_active = models.BooleanField(default=True, verbose_name="activée")
    max_per_user = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="max par utilisateur"
    )
    max_per_day = models.PositiveIntegerField(null=True, blank=True, verbose_name="max par jour")
    cooldown_days = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="délai entre déclenchements (jours)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "règle de fidélité"
        verbose_name_plural = "règles de fidélité"
        ordering = ("trigger", "name")
        indexes = [ # noqa: RUF012
            models.Index(fields=("trigger", "is_active"), name="loyalty_rule_trigger_active"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.trigger})"


# append-only ledger of points earned/spent per user
class PointTransaction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="point_transactions",
        db_index=True,
        verbose_name="utilisateur",
    )
    points = models.IntegerField(verbose_name="points")
    reason = models.CharField(max_length=200, verbose_name="motif")
    rule = models.ForeignKey(
        LoyaltyRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name="règle",
    )
    reference_type = models.CharField(max_length=30, blank=True, verbose_name="type de référence")
    reference_id = models.CharField(
        max_length=100, blank=True, verbose_name="identifiant de référence"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="créé le")

    class Meta:
        verbose_name = "transaction de points"
        verbose_name_plural = "transactions de points"
        ordering = ("-created_at", "-pk")
        indexes = [ # noqa: RUF012
            models.Index(fields=("user", "-created_at"), name="loyalty_point_user_created"),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.points:+d}"


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
