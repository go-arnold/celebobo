from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.messaging.domain.commands import PostMessage
from apps.messaging.domain.errors import ConversationNotFound
from apps.messaging.facades import ConversationFacade
from apps.messaging.selectors import ConversationSelector
from apps.realtime.adapters.db import db_call
from apps.realtime.conf import realtime_settings
from apps.realtime.domain.groups import STAFF, conversation_group, user_group
from apps.realtime.domain.protocol import ClientMessage, Envelope, ServerEvent, outbound
from apps.realtime.domain.rate_limit import TokenBucket
from apps.realtime.services.presence import PresenceService
from apps.realtime.services.relay import RealtimeRelay
from core.api.actor import actor_from_user
from core.container import container
from core.domain.actor import Actor, Role
from core.domain.errors import BusinessRuleViolation, DomainError

UNAUTHORIZED_CLOSE_CODE = 4401
MAX_BODY = 4000
MAX_ATTACHMENT = 500
MAX_CLIENT_ID = 64

type Handler = Callable[[Envelope], Awaitable[None]]


class RateLimited(BusinessRuleViolation):
    default_code = "rate_limited"
    default_detail = "Trop de messages. Patientez quelques secondes."


class NotSubscribed(BusinessRuleViolation):
    default_code = "not_subscribed"
    default_detail = "Abonnez-vous d'abord à cette discussion."


class GatewayConsumer(AsyncJsonWebsocketConsumer):
    actor: Actor
    display_name: str
    subscriptions: set[int]
    bucket: TokenBucket

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=UNAUTHORIZED_CLOSE_CODE)
            return
        settings = realtime_settings()
        self.actor = actor_from_user(user)
        self.display_name = f"{user.first_name} {user.last_name}".strip() or user.email
        self.subscriptions = set()
        self.bucket = TokenBucket(
            capacity=settings.burst, refill_per_second=settings.refill_per_second
        )
        await self.accept()
        await self._join(user_group(self._user_id))
        if self.actor.is_staff:
            await self._join(STAFF)
        if self.actor.role is Role.RESELLER and await _presence(
            PresenceService.connected, self._user_id
        ):
            await _relay_presence(self._user_id, online=True)
        await self.send_json(
            outbound(ServerEvent.READY, {"user_id": self._user_id, "role": self.actor.role.value})
        )

    async def disconnect(self, _close_code: int) -> None:
        if not hasattr(self, "actor"):
            return
        for conversation_id in list(self.subscriptions):
            await self._leave(conversation_group(conversation_id))
        await self._leave(user_group(self._user_id))
        if self.actor.is_staff:
            await self._leave(STAFF)
        if self.actor.role is Role.RESELLER and await _presence(
            PresenceService.disconnected, self._user_id
        ):
            await _relay_presence(self._user_id, online=False)

    async def receive_json(self, content: Any, **_: Any) -> None:
        ref = content.get("ref") if isinstance(content, dict) else None
        try:
            if not self.bucket.allow(monotonic()):
                raise RateLimited
            envelope = Envelope.parse(content)
            await self._handlers()[envelope.type](envelope)
        except DomainError as error:
            await self.send_json(
                outbound(
                    ServerEvent.ERROR,
                    {"code": error.code, "detail": error.detail},
                    ref=ref if isinstance(ref, str) else None,
                )
            )

    async def broadcast(self, message: dict[str, Any]) -> None:
        if message.get("skip_channel") == self.channel_name:
            return
        await self.send_json({"type": message["event"], "data": message["data"]})

    def _handlers(self) -> dict[ClientMessage, Handler]:
        return {
            ClientMessage.SUBSCRIBE: self._subscribe,
            ClientMessage.UNSUBSCRIBE: self._unsubscribe,
            ClientMessage.SEND: self._send_message,
            ClientMessage.TYPING_START: self._typing,
            ClientMessage.TYPING_STOP: self._typing,
            ClientMessage.READ: self._read,
            ClientMessage.PING: self._ping,
        }

    async def _subscribe(self, envelope: Envelope) -> None:
        conversation_id = envelope.integer("conversation_id")
        if not await _visible(self.actor, conversation_id):
            raise ConversationNotFound
        self.subscriptions.add(conversation_id)
        await self._join(conversation_group(conversation_id))
        await self.send_json(
            outbound(ServerEvent.SUBSCRIBED, {"conversation_id": conversation_id}, ref=envelope.ref)
        )

    async def _unsubscribe(self, envelope: Envelope) -> None:
        conversation_id = envelope.integer("conversation_id")
        self.subscriptions.discard(conversation_id)
        await self._leave(conversation_group(conversation_id))
        await self.send_json(
            outbound(
                ServerEvent.UNSUBSCRIBED, {"conversation_id": conversation_id}, ref=envelope.ref
            )
        )

    async def _send_message(self, envelope: Envelope) -> None:
        conversation_id = envelope.integer("conversation_id")
        command = PostMessage(
            body=envelope.text("body", limit=MAX_BODY),
            attachment=envelope.text("attachment", limit=MAX_ATTACHMENT),
            client_msg_id=envelope.text("client_msg_id", limit=MAX_CLIENT_ID),
        )
        message_id = await _post(self.actor, conversation_id, command)
        await self.send_json(
            outbound(
                ServerEvent.ACK,
                {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "client_msg_id": command.client_msg_id,
                },
                ref=envelope.ref,
            )
        )

    async def _typing(self, envelope: Envelope) -> None:
        conversation_id = envelope.integer("conversation_id")
        if conversation_id not in self.subscriptions:
            raise NotSubscribed
        await self.channel_layer.group_send(
            conversation_group(conversation_id),
            {
                "type": "broadcast",
                "event": ServerEvent.TYPING.value,
                "skip_channel": self.channel_name,
                "data": {
                    "conversation_id": conversation_id,
                    "user_id": self._user_id,
                    "name": self.display_name,
                    "typing": envelope.type is ClientMessage.TYPING_START,
                },
            },
        )

    async def _read(self, envelope: Envelope) -> None:
        conversation_id = envelope.integer("conversation_id")
        last = envelope.data.get("last_message_id")
        await _read(self.actor, conversation_id, last if isinstance(last, int) else None)

    async def _ping(self, envelope: Envelope) -> None:
        if self.actor.role is Role.RESELLER:
            await _presence(PresenceService.heartbeat, self._user_id)
        await self.send_json(outbound(ServerEvent.PONG, {}, ref=envelope.ref))

    async def _join(self, group: str) -> None:
        await self.channel_layer.group_add(group, self.channel_name)

    async def _leave(self, group: str) -> None:
        await self.channel_layer.group_discard(group, self.channel_name)

    @property
    def _user_id(self) -> int:
        if self.actor.user_id is None:
            raise ConversationNotFound
        return self.actor.user_id


@db_call
def _visible(actor: Actor, conversation_id: int) -> bool:
    return ConversationSelector().visible(actor, conversation_id)


@db_call
def _post(actor: Actor, conversation_id: int, command: PostMessage) -> int:
    return container.resolve(ConversationFacade).post(actor, conversation_id, command).id


@db_call
def _read(actor: Actor, conversation_id: int, last_message_id: int | None) -> int:
    return container.resolve(ConversationFacade).read(actor, conversation_id, last_message_id)


@db_call
def _presence(operation: Callable[[PresenceService, int], Any], user_id: int) -> Any:
    return operation(container.resolve(PresenceService), user_id)


@db_call
def _relay_presence(user_id: int, *, online: bool) -> None:
    container.resolve(RealtimeRelay).presence_changed(user_id, online=online, availability=None)
