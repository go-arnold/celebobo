from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.domain.consents import ConsentKind, ConsentSource
from apps.accounts.domain.enums import (
    ACCOUNT_ROLES,
    ROLE_LABELS,
    AddressLabel,
    Availability,
)
from apps.accounts.managers import UserManager
from core.domain.actor import Role

ROLE_CHOICES = [(role.value, ROLE_LABELS[role]) for role in ACCOUNT_ROLES]
AVAILABILITY_CHOICES = [(item.value, item.label) for item in Availability]
ADDRESS_LABEL_CHOICES = [(item.value, item.label) for item in AddressLabel]
CONSENT_KIND_CHOICES = [(item.value, item.label) for item in ConsentKind]
CONSENT_SOURCE_CHOICES = [(item.value, item.value) for item in ConsentSource]


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    email = models.EmailField("adresse e-mail", unique=True)
    # E.164 (+243 and 9 digits), one account per phone (see the constraint below); required for
    # clients and resellers by the services, NULL (no phone) for staff and anonymised accounts
    phone_number = models.CharField(  # noqa: DJ001
        "téléphone",
        max_length=20,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^\+243[89]\d{8}$")],
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
    # when the client joined the reseller: referral points run for 12 months from then
    invited_at = models.DateTimeField("invité le", null=True, blank=True)
    availability = models.CharField(
        "disponibilité",
        max_length=8,
        choices=AVAILABILITY_CHOICES,
        default=Availability.OFFLINE.value,
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
    # retention: what other parts of the shop still held about the client was erased (on
    # anonymisation for inactivity, or 3 years after the client deleted the account)
    personal_data_erased_at = models.DateTimeField(
        "données personnelles effacées le", null=True, blank=True
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["first_name", "last_name"]

    objects: ClassVar[UserManager] = UserManager()  # type: ignore[assignment]

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ("-date_joined",)
        constraints = (
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.UniqueConstraint(
                fields=("phone_number",),
                condition=models.Q(phone_number__isnull=False) & ~models.Q(phone_number=""),
                name="accounts_user_phone_unique",
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


class ConsentQuerySet(models.QuerySet["Consent"]):
    # the version each consent still open was accepted on last (latest acceptance wins)
    def open_versions(self, user_id: int) -> dict[ConsentKind, str]:
        rows = (
            self.filter(user_id=user_id, withdrawn_at__isnull=True)
            .order_by("kind", "-accepted_at", "-pk")
            .distinct("kind")
            .values_list("kind", "version")
        )
        return {ConsentKind(kind): version for kind, version in rows}


# one row per acceptance, kept as proof: accepting again (e.g. a new version of the document) adds
# a row, withdrawing sets withdrawn_at on the rows still open
class Consent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    kind = models.CharField("consentement", max_length=16, choices=CONSENT_KIND_CHOICES)
    version = models.CharField("version acceptée", max_length=20, blank=True)
    source = models.CharField("donné depuis", max_length=16, choices=CONSENT_SOURCE_CHOICES)
    accepted_at = models.DateTimeField("accepté le", default=timezone.now)
    withdrawn_at = models.DateTimeField("retiré le", null=True, blank=True)

    objects = ConsentQuerySet.as_manager()

    class Meta:
        verbose_name = "consentement"
        verbose_name_plural = "consentements"
        ordering = ("-accepted_at", "-pk")
        indexes = (models.Index(fields=("user", "kind"), name="accounts_consent_user_kind"),)

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.user_id} ({self.version or '-'})"
