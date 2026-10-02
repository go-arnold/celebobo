from collections.abc import Callable
from datetime import datetime
from typing import Any

from apps.messaging.domain.commands import OpenSupport, PostMessage
from apps.messaging.domain.enums import ConversationKind, ConversationStatus, MessageKind
from apps.messaging.domain.errors import (
    ConversationClosedError,
    EmptyMessage,
    NotASupportConversation,
)
from apps.messaging.domain.notifications import preview
from apps.messaging.models import Conversation, Message
from apps.messaging.repositories import (
    ConversationRepository,
    MessageRepository,
    NotificationRepository,
    ParticipantRepository,
)
from core.domain.actor import Actor, Role
from core.domain.errors import Unauthenticated


class ConversationService:
    def __init__(
        self,
        conversations: ConversationRepository,
        messages: MessageRepository,
        participants: ParticipantRepository,
        notifications: NotificationRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._participants = participants
        self._notifications = notifications
        self._clock = clock

    def open_for_order(self, *, order_id: int, number: str, client_id: int) -> Conversation:
        existing = self._conversations.for_order(order_id)
        if existing is not None:
            return existing
        conversation = self._conversations.create(
            kind=ConversationKind.ORDER.value,
            order_id=order_id,
            client_id=client_id,
            subject=f"Commande {number}",
        )
        self._participants.join(conversation, client_id)
        self.system_message(
            conversation,
            f"Discussion exclusivement consacrée à la commande {number}.",
            {"event": "order_placed", "order_id": order_id},
        )
        return conversation

    def open_support(self, client_id: int, command: OpenSupport) -> tuple[Conversation, Message]:
        conversation = self._conversations.create(
            kind=ConversationKind.SUPPORT.value,
            client_id=client_id,
            subject=" ".join(command.subject.split()) or preview(command.message, limit=60),
        )
        self._participants.join(conversation, client_id)
        message, _ = self.post(
            Actor(role=Role.CLIENT, user_id=client_id),
            conversation,
            PostMessage(body=command.message),
        )
        return conversation, message

    def post(
        self, actor: Actor, conversation: Conversation, command: PostMessage
    ) -> tuple[Message, bool]:
        body = command.body.strip()
        if not body and not command.attachment:
            raise EmptyMessage
        if not conversation.is_open:
            raise ConversationClosedError
        sender_id = actor.user_id
        if sender_id is not None and (
            existing := self._messages.by_client_id(sender_id, command.client_msg_id)
        ):
            return existing, False
        message = self._messages.create(
            conversation,
            sender_id=sender_id,
            kind=MessageKind.TEXT.value,
            body=body,
            attachment=command.attachment,
            client_msg_id=command.client_msg_id,
        )
        if sender_id is not None:
            self._participants.mark_read(conversation, sender_id, message.pk)
        return message, True

    def mark_read(self, actor: Actor, conversation: Conversation, message_id: int | None) -> int:
        user_id = _require(actor)
        latest = self._messages.latest_id(conversation)
        target = latest if message_id is None else min(message_id, latest)
        read_up_to = self._participants.mark_read(conversation, user_id, target)
        if read_up_to >= latest:
            self._notifications.mark_conversation_read(user_id, conversation.pk, self._clock())
        return read_up_to

    def close(self, conversation: Conversation, *, note: str) -> bool:
        if not conversation.is_open:
            return False
        conversation.status = ConversationStatus.CLOSED.value
        conversation.closed_at = self._clock()
        self._conversations.save(conversation, fields=("status", "closed_at"))
        self.system_message(conversation, note, {"event": "closed"})
        return True

    def reopen(self, conversation: Conversation) -> bool:
        if conversation.is_open:
            return False
        conversation.status = ConversationStatus.OPEN.value
        conversation.closed_at = None
        self._conversations.save(conversation, fields=("status", "closed_at"))
        self.system_message(conversation, "Discussion rouverte.", {"event": "reopened"})
        return True

    def assign(self, conversation: Conversation, reseller_id: int, reseller_name: str) -> None:
        if conversation.kind != ConversationKind.SUPPORT.value:
            raise NotASupportConversation
        self._set_reseller(conversation, reseller_id, reseller_name)

    def sync_order_reseller(
        self, order_id: int, reseller_id: int | None, reseller_name: str
    ) -> Conversation | None:
        conversation = self._conversations.for_order(order_id, for_update=True)
        if conversation is None or conversation.assigned_reseller_id == reseller_id:
            return conversation
        if reseller_id is None:
            conversation.assigned_reseller_id = None
            self._conversations.save(conversation, fields=("assigned_reseller",))
            self.system_message(
                conversation, "Le revendeur a quitté la discussion.", {"event": "unassigned"}
            )
            return conversation
        self._set_reseller(conversation, reseller_id, reseller_name)
        return conversation

    def close_for_order(self, order_id: int, status_label: str) -> Conversation | None:
        conversation = self._conversations.for_order(order_id, for_update=True)
        if conversation is not None:
            self.close(conversation, note=f"Commande {status_label.lower()} : discussion clôturée.")
        return conversation

    def system_message(
        self, conversation: Conversation, body: str, metadata: dict[str, Any]
    ) -> Message:
        return self._messages.create(
            conversation,
            sender_id=None,
            kind=MessageKind.SYSTEM.value,
            body=body,
            metadata=metadata,
        )

    def _set_reseller(self, conversation: Conversation, reseller_id: int, name: str) -> None:
        conversation.assigned_reseller_id = reseller_id
        self._conversations.save(conversation, fields=("assigned_reseller",))
        self._participants.join(conversation, reseller_id)
        self.system_message(
            conversation,
            f"{name} a rejoint la discussion.",
            {"event": "assigned", "reseller_id": reseller_id},
        )


def _require(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id
