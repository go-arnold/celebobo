from django.contrib import admin

from apps.resellers.models import ResellerApplication


@admin.register(ResellerApplication)
class ResellerApplicationAdmin(admin.ModelAdmin[ResellerApplication]):
    list_display = ("first_name", "last_name", "email", "city", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("first_name", "last_name", "email", "phone_number")
    raw_id_fields = ("applicant", "reseller", "reviewed_by")
    readonly_fields = ("created_at",)
