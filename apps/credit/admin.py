from django.contrib import admin

from apps.credit.models import CreditEntry


@admin.register(CreditEntry)
class CreditEntryAdmin(admin.ModelAdmin[CreditEntry]):
    list_display = ("user", "kind", "amount", "remaining", "expires_at", "order", "created_at")
    list_filter = ("kind",)
    raw_id_fields = ("user", "source", "order")
