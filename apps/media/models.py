from django.conf import settings
from django.db import models

from apps.media.domain.policies import UploadPurpose

PURPOSE_CHOICES = [(item.value, item.value) for item in UploadPurpose]


class UploadedMedia(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="uploads"
    )
    purpose = models.CharField(max_length=24, choices=PURPOSE_CHOICES)
    public_id = models.CharField(max_length=255, unique=True)
    url = models.URLField(max_length=500)
    format = models.CharField(max_length=10)
    bytes = models.PositiveIntegerField()
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "fichier"
        verbose_name_plural = "fichiers"
        ordering = ("-created_at", "-pk")

    def __str__(self) -> str:
        return self.public_id
