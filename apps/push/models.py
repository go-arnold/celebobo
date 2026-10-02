from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=255, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "abonnement push"
        verbose_name_plural = "abonnements push"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.user_id} · {self.user_agent[:40]}"
