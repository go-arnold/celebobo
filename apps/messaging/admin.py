from django.contrib import admin

from apps.messaging.models import Conversation, Message, Notification


class MessageInline(admin.TabularInline[Message, Conversation]):
    model = Message
    extra = 0
    can_delete = False
    readonly_fields = ("sender", "kind", "body", "attachment", "created_at")
    ordering = ("pk",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin[Conversation]):
    list_display = ("__str__", "kind", "status", "client", "assigned_reseller", "last_message_at")
    list_filter = ("kind", "status")
    search_fields = ("subject", "client__email", "order__number")
    raw_id_fields = ("client", "assigned_reseller", "order")
    inlines = (MessageInline,)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin[Notification]):
    list_display = ("title", "recipient", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    raw_id_fields = ("recipient", "conversation", "order")
