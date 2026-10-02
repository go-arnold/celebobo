import json
from dataclasses import asdict
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

from apps.accounts.selectors import DirectorySelector
from apps.messaging.selectors import ConversationSelector, NotificationSelector
from apps.orders.selectors import order_ref
from apps.realtime.domain.groups import STAFF, conversation_group, user_group
from apps.realtime.domain.protocol import ServerEvent
from apps.realtime.services.contracts import Broadcaster
from core.domain.actor import Actor


def jsonable(value: Any) -> Any:
    payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


class RealtimeRelay:
    def __init__(
        self,
        broadcaster: Broadcaster,
        *,
        conversations: ConversationSelector,
        notifications: NotificationSelector,
        directory: DirectorySelector,
    ) -> None:
        self._broadcaster = broadcaster
        self._conversations = conversations
        self._notifications = notifications
        self._directory = directory

    def message_posted(self, conversation_id: int, message_id: int) -> None:
        message = self._conversations.message(message_id)
        self._broadcaster.send(
            [conversation_group(conversation_id)],
            ServerEvent.MESSAGE_CREATED,
            {"conversation_id": conversation_id, "message": jsonable(message)},
        )
        self.conversation_updated(conversation_id)

    def conversation_updated(self, conversation_id: int) -> None:
        audience = self._conversations.audience(conversation_id)
        recipients = [user_group(audience.client_id)]
        if audience.reseller_id is not None:
            recipients.append(user_group(audience.reseller_id))
        self._broadcaster.send(
            [*recipients, STAFF],
            ServerEvent.CONVERSATION_UPDATED,
            {"conversation_id": conversation_id},
        )

    def conversation_read(self, conversation_id: int, user_id: int, message_id: int) -> None:
        self._broadcaster.send(
            [conversation_group(conversation_id)],
            ServerEvent.READ,
            {"conversation_id": conversation_id, "user_id": user_id, "message_id": message_id},
        )
        self.unread_counts(user_id)

    def conversation_lifecycle(
        self, event: ServerEvent, conversation_id: int, **extra: Any
    ) -> None:
        self._broadcaster.send(
            [conversation_group(conversation_id), STAFF],
            event,
            {"conversation_id": conversation_id, **extra},
        )
        self.conversation_updated(conversation_id)

    def notification_created(self, notification_id: int, recipient_id: int) -> None:
        notification = self._notifications.one(notification_id)
        self._broadcaster.send(
            [user_group(recipient_id)],
            ServerEvent.NOTIFICATION_CREATED,
            {"notification": jsonable(notification)},
        )
        self.unread_counts(recipient_id)

    def unread_counts(self, user_id: int) -> None:
        contact = self._directory.contacts([user_id]).get(user_id)
        if contact is None:
            return
        counts = self._notifications.counts(Actor(role=contact.role, user_id=user_id))
        self._broadcaster.send([user_group(user_id)], ServerEvent.UNREAD_COUNTS, jsonable(counts))

    def order_event(self, event: ServerEvent, order_id: int, **extra: Any) -> None:
        order = order_ref(order_id)
        recipients = [user_group(order.client_id), STAFF]
        if order.reseller_id is not None:
            recipients.append(user_group(order.reseller_id))
        self._broadcaster.send(
            recipients,
            event,
            {
                "order_id": order.id,
                "number": order.number,
                "status": order.status.value,
                "total": str(order.total),
                **extra,
            },
        )

    def presence_changed(self, user_id: int, *, online: bool, availability: str | None) -> None:
        self._broadcaster.send(
            [STAFF],
            ServerEvent.PRESENCE_CHANGED,
            {"user_id": user_id, "online": online, "availability": availability},
        )
