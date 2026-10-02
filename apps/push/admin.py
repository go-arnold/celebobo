from django.contrib import admin

from apps.push.models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin[PushSubscription]):
    list_display = ("user", "user_agent", "failures", "created_at", "last_used_at")
    raw_id_fields = ("user",)
    readonly_fields = ("endpoint", "p256dh", "auth")
