from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db.models import F, Q
from django.db.models.functions import Greatest

from apps.messaging.domain.enums import NotificationKind, ProposalStatus
from apps.messaging.models import Conversation, Message, Notification, Participant, PriceProposal


class ConversationRepository:
    def create(self, **fields: Any) -> Conversation:
        return Conversation.objects.create(**fields)

    def get(self, conversation_id: int, *, for_update: bool = False) -> Conversation | None:
        queryset = Conversation.objects.select_for_update() if for_update else Conversation.objects
        return queryset.filter(pk=conversation_id).first()

    def for_order(self, order_id: int, *, for_update: bool = False) -> Conversation | None:
        queryset = Conversation.objects.select_for_update() if for_update else Conversation.objects
        return queryset.filter(order_id=order_id).first()

    def id_for_order(self, order_id: int) -> int | None:
        return Conversation.objects.filter(order_id=order_id).values_list("pk", flat=True).first()

    def save(self, conversation: Conversation, *, fields: Iterable[str]) -> None:
        conversation.save(update_fields=[*fields])


class MessageRepository:
    def create(self, conversation: Conversation, **fields: Any) -> Message:
        message = Message.objects.create(conversation=conversation, **fields)
        Conversation.objects.filter(pk=conversation.pk).update(last_message_at=message.created_at)
        conversation.last_message_at = message.created_at
        return message

    def by_client_id(self, sender_id: int, client_msg_id: str) -> Message | None:
        if not client_msg_id:
            return None
        return Message.objects.filter(sender_id=sender_id, client_msg_id=client_msg_id).first()

    def latest_id(self, conversation: Conversation) -> int:
        return conversation.messages.order_by("-pk").values_list("pk", flat=True).first() or 0


class ParticipantRepository:
    def join(self, conversation: Conversation, user_id: int) -> Participant:
        participant, _ = Participant.objects.get_or_create(
            conversation=conversation, user_id=user_id
        )
        return participant

    def mark_read(self, conversation: Conversation, user_id: int, message_id: int) -> int:
        self.join(conversation, user_id)
        Participant.objects.filter(conversation=conversation, user_id=user_id).update(
            last_read_message_id=Greatest(F("last_read_message_id"), message_id)
        )
        return int(
            Participant.objects.filter(conversation=conversation, user_id=user_id)
            .values_list("last_read_message_id", flat=True)
            .get()
        )


class ProposalRepository:
    def create(self, **fields: Any) -> PriceProposal:
        return PriceProposal.objects.create(**fields)

    def get(self, proposal_id: int, *, for_update: bool = False) -> PriceProposal | None:
        queryset = (
            PriceProposal.objects.select_for_update() if for_update else PriceProposal.objects
        )
        return queryset.select_related("conversation").filter(pk=proposal_id).first()

    def supersede_pending(self, conversation: Conversation, order_item_id: int) -> None:
        PriceProposal.objects.filter(
            conversation=conversation,
            order_item_id=order_item_id,
            status=ProposalStatus.PENDING.value,
        ).update(status=ProposalStatus.SUPERSEDED.value)

    def answer(self, proposal: PriceProposal, status: ProposalStatus, at: datetime) -> None:
        proposal.status = status.value
        proposal.responded_at = at
        proposal.save(update_fields=["status", "responded_at"])
        message = proposal.message
        message.metadata = {**message.metadata, "status": status.value}
        message.save(update_fields=["metadata"])


class NotificationRepository:
    def create_many(self, notifications: Iterable[Notification]) -> list[Notification]:
        return Notification.objects.bulk_create(list(notifications))

    def unread_message_alert_exists(self, recipient_id: int, conversation_id: int) -> bool:
        return Notification.objects.filter(
            recipient_id=recipient_id,
            conversation_id=conversation_id,
            kind=NotificationKind.NEW_MESSAGE.value,
            is_read=False,
        ).exists()

    def mark_read(self, recipient_id: int, notification_id: int, at: datetime) -> bool:
        return bool(
            Notification.objects.filter(pk=notification_id, recipient_id=recipient_id).update(
                is_read=True, read_at=at
            )
        )

    def mark_all_read(self, recipient_id: int, at: datetime) -> int:
        return Notification.objects.filter(recipient_id=recipient_id, is_read=False).update(
            is_read=True, read_at=at
        )

    def mark_conversation_read(self, recipient_id: int, conversation_id: int, at: datetime) -> None:
        Notification.objects.filter(
            Q(recipient_id=recipient_id)
            & Q(conversation_id=conversation_id)
            & Q(kind=NotificationKind.NEW_MESSAGE.value)
            & Q(is_read=False)
        ).update(is_read=True, read_at=at)
