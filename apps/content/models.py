import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.content.domain.enums import ContactStatus, ContactSubject

SUBJECT_CHOICES = [(item.value, item.label) for item in ContactSubject]
STATUS_CHOICES = [(item.value, item.value) for item in ContactStatus]


class ContactMessage(models.Model):
    name = models.CharField("nom", max_length=120)
    email = models.EmailField("e-mail")
    phone = models.CharField("téléphone", max_length=20, blank=True)
    subject = models.CharField("sujet", max_length=16, choices=SUBJECT_CHOICES)
    message = models.TextField("message")
    status = models.CharField(
        max_length=8, choices=STATUS_CHOICES, default=ContactStatus.NEW.value, db_index=True
    )
    note = models.TextField("note interne", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "message de contact"
        verbose_name_plural = "messages de contact"
        ordering = ("-created_at", "-pk")

    def __str__(self) -> str:
        return f"{self.name} — {self.get_subject_display()}"


class Subscriber(models.Model):
    email = models.EmailField("e-mail")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source = models.CharField(max_length=40, blank=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "abonné"
        verbose_name_plural = "abonnés"
        ordering = ("-subscribed_at",)
        constraints = (
            models.UniqueConstraint(Lower("email"), name="content_subscriber_email_unique"),
        )

    def __str__(self) -> str:
        return self.email

    @property
    def is_active(self) -> bool:
        return self.unsubscribed_at is None


class Page(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=160)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField()
    is_published = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "page"
        verbose_name_plural = "pages"
        ordering = ("position", "title")

    def __str__(self) -> str:
        return self.title


class FaqEntry(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    category = models.CharField(max_length=60, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        verbose_name = "question fréquente"
        verbose_name_plural = "questions fréquentes"
        ordering = ("category", "position", "pk")

    def __str__(self) -> str:
        return self.question


class Banner(models.Model):
    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=255, blank=True)
    image = models.URLField(max_length=500)
    link_url = models.CharField(max_length=300, blank=True)
    link_label = models.CharField(max_length=60, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "bannière"
        verbose_name_plural = "bannières"
        ordering = ("position", "pk")

    def __str__(self) -> str:
        return self.title


class SiteSettings(models.Model):
    usd_to_cdf = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("2800.00"))
    hotline = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    opening_hours = models.JSONField(default=list, blank=True)
    payment_methods = models.JSONField(default=list, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    newsletter_code = models.CharField(max_length=30, blank=True)
    newsletter_discount = models.PositiveSmallIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "paramètres du site"
        verbose_name_plural = "paramètres du site"

    def __str__(self) -> str:
        return "Paramètres du site"
