from django.contrib import admin

from apps.audit.models import EventRecord


@admin.register(EventRecord)
class EventRecordAdmin(admin.ModelAdmin[EventRecord]):
    list_display = ("event_type", "actor_id", "occurred_at")
    list_filter = ("event_type",)
    readonly_fields = (
        "event_id",
        "event_type",
        "actor_id",
        "payload",
        "occurred_at",
        "recorded_at",
    )

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: EventRecord | None = None) -> bool:
        return False
