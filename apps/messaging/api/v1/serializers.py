from typing import Any

from rest_framework import serializers

from apps.messaging.domain.enums import ConversationKind, ConversationStatus, NotificationKind
from core.api.fields import MAX_INTEGER


class ConversationFiltersInput(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(
        choices=[item.value for item in ConversationKind], required=False
    )
    status = serializers.ChoiceField(
        choices=[item.value for item in ConversationStatus], required=False
    )
    unread = serializers.BooleanField(required=False, default=False)
    search = serializers.CharField(max_length=100, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "kind" in attrs:
            attrs["kind"] = ConversationKind(attrs["kind"])
        if "status" in attrs:
            attrs["status"] = ConversationStatus(attrs["status"])
        return attrs


class OpenSupportInput(serializers.Serializer[Any]):
    subject = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    message = serializers.CharField(max_length=4000)


class PostMessageInput(serializers.Serializer[Any]):
    body = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    attachment = serializers.URLField(max_length=500, required=False, allow_blank=True, default="")
    client_msg_id = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )


class ReadInput(serializers.Serializer[Any]):
    last_message_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )


class AssignConversationInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)


class ProposePriceInput(serializers.Serializer[Any]):
    item_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    new_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class RespondProposalInput(serializers.Serializer[Any]):
    accept = serializers.BooleanField()


class MessageQueryInput(serializers.Serializer[Any]):
    before = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=30)


class NotificationQueryInput(serializers.Serializer[Any]):
    unread = serializers.BooleanField(required=False, default=False)
    kind = serializers.ChoiceField(
        choices=[item.value for item in NotificationKind], required=False
    )


class ParticipantOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.CharField()
    avatar = serializers.CharField()


class MessageOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    conversation_id = serializers.IntegerField()
    kind = serializers.CharField()
    body = serializers.CharField()
    attachment = serializers.CharField()
    metadata = serializers.DictField()
    sender = ParticipantOutput(allow_null=True)
    client_msg_id = serializers.CharField()
    created_at = serializers.DateTimeField()


class ConversationOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    status = serializers.CharField()
    subject = serializers.CharField()
    order_id = serializers.IntegerField(allow_null=True)
    order_number = serializers.CharField(allow_null=True)
    client = ParticipantOutput()
    reseller = ParticipantOutput(allow_null=True)
    last_message = MessageOutput(allow_null=True)
    unread_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    last_message_at = serializers.DateTimeField(allow_null=True)


class ReadOutput(serializers.Serializer[Any]):
    last_read_message_id = serializers.IntegerField()


class NotificationOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    link = serializers.CharField()
    is_read = serializers.BooleanField()
    conversation_id = serializers.IntegerField(allow_null=True)
    order_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()


class UnreadCountsOutput(serializers.Serializer[Any]):
    notifications = serializers.IntegerField()
    conversations = serializers.IntegerField()


class ReadAllOutput(serializers.Serializer[Any]):
    updated = serializers.IntegerField()
