from decimal import Decimal
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.domain.enums import (
    ACCOUNT_ROLES,
    MAX_COMMISSION_RATE,
    ROLE_LABELS,
    AddressLabel,
    Availability,
)
from apps.accounts.managers import UserManager
from core.domain.actor import Role

ROLE_CHOICES = [(role.value, ROLE_LABELS[role]) for role in ACCOUNT_ROLES]
AVAILABILITY_CHOICES = [(item.value, item.label) for item in Availability]
ADDRESS_LABEL_CHOICES = [(item.value, item.label) for item in AddressLabel]
DEFAULT_COMMISSION_RATE = Decimal("0.070")


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    email = models.EmailField("adresse e-mail", unique=True)
    phone_number = models.CharField(
        "téléphone",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^\+?[\d\s().-]{7,20}$")],
    )
    avatar = models.URLField("photo", max_length=500, blank=True)
    role = models.CharField(
        "rôle", max_length=16, choices=ROLE_CHOICES, default=Role.CLIENT.value, db_index=True
    )
    referral_code = models.CharField(
        "code revendeur",
        max_length=4,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^\d{4}$")],
    )
    invited_by = models.ForeignKey(
        "self",
        verbose_name="invité par",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitees",
    )
    availability = models.CharField(
        "disponibilité",
        max_length=8,
        choices=AVAILABILITY_CHOICES,
        default=Availability.OFFLINE.value,
    )
    commission_rate = models.DecimalField(
        "taux de commission",
        max_digits=4,
        decimal_places=3,
        default=DEFAULT_COMMISSION_RATE,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(MAX_COMMISSION_RATE)],
    )
    manager = models.ForeignKey(
        "self",
        verbose_name="responsable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_resellers",
    )
    last_seen_at = models.DateTimeField("vu pour la dernière fois", null=True, blank=True)
    deleted_at = models.DateTimeField("supprimé le", null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["first_name", "last_name"]

    objects: ClassVar[UserManager] = UserManager()  # type: ignore[assignment]

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ("-date_joined",)
        constraints = (
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.CheckConstraint(
                condition=models.Q(commission_rate__gte=0)
                & models.Q(commission_rate__lte=MAX_COMMISSION_RATE),
                name="accounts_user_commission_rate_range",
            ),
        )

    def __str__(self) -> str:
        return self.get_full_name() or self.email

    @property
    def account_role(self) -> Role:
        return Role(self.role)


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(
        max_length=8, choices=ADDRESS_LABEL_CHOICES, default=AddressLabel.HOME.value
    )
    recipient = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    line1 = models.CharField(max_length=255)
    quarter = models.CharField(max_length=120)
    city = models.CharField(max_length=120)
    country = models.CharField(max_length=80)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "adresse"
        verbose_name_plural = "adresses"
        ordering = ("-is_default", "-created_at")
        constraints = (
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(is_default=True),
                name="accounts_address_single_default",
            ),
        )

    def __str__(self) -> str:
        return f"{self.recipient} — {self.line1}, {self.city}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="notification_preference"
    )
    preferences = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "préférences de notification"
        verbose_name_plural = "préférences de notification"

    def __str__(self) -> str:
        return f"Préférences de {self.user}"
