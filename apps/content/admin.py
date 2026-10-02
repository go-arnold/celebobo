from django.contrib import admin

from apps.content.models import Banner, ContactMessage, FaqEntry, Page, SiteSettings, Subscriber


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin[ContactMessage]):
    list_display = ("name", "email", "subject", "status", "created_at")
    list_filter = ("status", "subject")
    search_fields = ("name", "email", "message")
    raw_id_fields = ("user", "handled_by")


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin[Subscriber]):
    list_display = ("email", "source", "subscribed_at", "unsubscribed_at")
    search_fields = ("email",)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin[Page]):
    list_display = ("title", "slug", "is_published", "position")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(FaqEntry)
class FaqEntryAdmin(admin.ModelAdmin[FaqEntry]):
    list_display = ("question", "category", "position", "is_published")
    list_filter = ("category", "is_published")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin[Banner]):
    list_display = ("title", "position", "is_active", "starts_at", "ends_at")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin[SiteSettings]):
    def has_add_permission(self, request: object) -> bool:
        return not SiteSettings.objects.exists()
