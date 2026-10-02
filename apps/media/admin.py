from django.contrib import admin

from apps.media.models import UploadedMedia


@admin.register(UploadedMedia)
class UploadedMediaAdmin(admin.ModelAdmin[UploadedMedia]):
    list_display = ("public_id", "purpose", "owner", "bytes", "created_at")
    list_filter = ("purpose",)
    search_fields = ("public_id",)
    raw_id_fields = ("owner",)
