from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.resellers.domain.enums import ApplicationStatus

STATUS_CHOICES = [(status.value, status.label) for status in ApplicationStatus]


class ResellerApplication(models.Model):
    first_name = models.CharField("prénom", max_length=80)
    last_name = models.CharField("nom", max_length=80)
    email = models.EmailField("adresse e-mail")
    phone_number = models.CharField("téléphone", max_length=20)
    city = models.CharField("ville", max_length=120)
    message = models.TextField("motivation", blank=True)
    status = models.CharField(
        "statut",
        max_length=8,
        choices=STATUS_CHOICES,
        default=ApplicationStatus.PENDING.value,
        db_index=True,
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reseller_applications",
    )
    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField("traitée le", null=True, blank=True)
    decision_note = models.CharField("motif", max_length=500, blank=True)
    created_at = models.DateTimeField("reçue le", auto_now_add=True)

    class Meta:
        verbose_name = "candidature revendeur"
        verbose_name_plural = "candidatures revendeur"
        ordering = ("-created_at", "-pk")
        constraints = (
            models.UniqueConstraint(
                Lower("email"),
                condition=models.Q(status=ApplicationStatus.PENDING.value),
                name="resellers_application_single_pending",
            ),
        )

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} <{self.email}>"

    @property
    def application_status(self) -> ApplicationStatus:
        return ApplicationStatus(self.status)
