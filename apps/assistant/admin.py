from django.contrib import admin

from apps.assistant.models import AssistantMessage, AssistantSession


class MessageInline(admin.TabularInline[AssistantMessage, AssistantSession]):
    model = AssistantMessage
    extra = 0
    can_delete = False
    fields = ("role", "content", "sentiment", "topic", "input_tokens", "output_tokens", "cost")
    readonly_fields = fields


@admin.register(AssistantSession)
class AssistantSessionAdmin(admin.ModelAdmin[AssistantSession]):
    list_display = ("title", "user", "message_count", "updated_at")
    raw_id_fields = ("user",)
    inlines = (MessageInline,)
