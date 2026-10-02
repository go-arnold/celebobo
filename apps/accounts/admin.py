from typing import ClassVar

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Address, NotificationPreference, User


class AddressInline(admin.TabularInline[Address, User]):
    model = Address
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin[User]):
    ordering = ("-date_joined",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active", "is_staff", "availability")
    search_fields = ("email", "first_name", "last_name", "phone_number", "referral_code")
    readonly_fields = ("date_joined", "last_login", "last_seen_at", "deleted_at")
    raw_id_fields = ("invited_by", "manager")
    inlines: ClassVar = [AddressInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "phone_number", "avatar")}),
        ("Rôle", {"fields": ("role", "referral_code", "invited_by", "manager")}),
        ("Revendeur", {"fields": ("availability", "commission_rate")}),
        (
            "Accès",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("date_joined", "last_login", "last_seen_at", "deleted_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin[NotificationPreference]):
    list_display = ("user", "updated_at")
    raw_id_fields = ("user",)
