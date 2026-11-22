from django.contrib import admin

from apps.warranty.models import Claim


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin[Claim]):
    list_display = ("id", "order", "client", "kind", "status", "outcome", "created_at")
    list_filter = ("kind", "status", "outcome")
    raw_id_fields = ("order", "item", "client", "handled_by")
    readonly_fields = ("created_at",)
