from django.contrib import admin

from apps.documents.models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin[Job]):
    list_display = ("kind", "format", "status", "owner", "created_at", "finished_at")
    list_filter = ("kind", "status")
    raw_id_fields = ("owner",)
    exclude = ("upload",)
    readonly_fields = ("file", "filename", "size", "summary", "error", "finished_at")
