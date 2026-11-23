from django.contrib import admin

from apps.cagnotte.models import Campaign, Reward


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin[Campaign]):
    list_display = ("name", "kind", "percent", "starts_at", "ends_at")
    list_filter = ("kind",)
    search_fields = ("name",)


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin[Reward]):
    list_display = ("order", "campaign", "kind", "payout", "amount", "kept", "status")
    list_filter = ("status", "payout")
    raw_id_fields = ("order", "client", "paid_by")
