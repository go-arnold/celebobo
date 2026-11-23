from django.contrib import admin

from apps.standing.models import ResellerLevel, Sanction


@admin.register(ResellerLevel)
class ResellerLevelAdmin(admin.ModelAdmin[ResellerLevel]):
    list_display = ("reseller", "level", "sales", "rating", "reviewed_at")
    list_filter = ("level",)
    raw_id_fields = ("reseller",)


@admin.register(Sanction)
class SanctionAdmin(admin.ModelAdmin[Sanction]):
    list_display = ("reseller", "kind", "status", "urgent", "starts_at", "ends_at", "created_at")
    list_filter = ("kind", "status")
    raw_id_fields = ("reseller", "created_by", "decided_by")
