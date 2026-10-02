from django.db import models


class EventRecord(models.Model):
    event_id = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=160, db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "événement"
        verbose_name_plural = "événements"
        ordering = ("-occurred_at",)

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.occurred_at:%Y-%m-%d %H:%M}"
