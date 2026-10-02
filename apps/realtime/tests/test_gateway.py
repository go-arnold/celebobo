from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIClient

from apps.accounts.facades import RealtimeAccessFacade
from apps.accounts.models import User
from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.messaging.models import Conversation
from apps.orders.models import Order
from apps.orders.tests.conftest import ADDRESS
from config.asgi import application
from core.container import container
from core.domain.actor import Actor, Role

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]

ORIGIN = (b"origin", b"https://app.test")


def ticket_for(user: User) -> str:
    actor = Actor(role=Role(user.role), user_id=user.pk)
    return container.resolve(RealtimeAccessFacade).issue_ticket(actor).ticket


async def open_socket(user: User, *, origin: tuple[bytes, bytes] = ORIGIN) -> WebsocketCommunicator:
    ticket = await sync_to_async(ticket_for)(user)
    socket = WebsocketCommunicator(application, f"/ws/?ticket={ticket}", headers=[origin])
    connected, _ = await socket.connect()
    assert connected
    ready = await socket.receive_json_from()
    assert ready["type"] == "session.ready"
    return socket


async def receive_until(
    socket: WebsocketCommunicator, event_type: str, *, attempts: int = 10
) -> dict[str, Any]:
    for _ in range(attempts):
        message: dict[str, Any] = await socket.receive_json_from(timeout=2)
        if message["type"] == event_type:
            return message
    raise AssertionError(f"{event_type} not received")


@pytest.fixture
def client_user(transactional_db) -> User:
    return UserFactory.create(first_name="Aline", last_name="Mbuyi")


@pytest.fixture
def reseller(transactional_db) -> User:
    return ResellerFactory.create(first_name="Patrick", last_name="Kabasele")


@pytest.fixture
def manager(transactional_db) -> User:
    return ManagerFactory.create()


@pytest.fixture
def rest() -> Callable[[User], APIClient]:
    def client(user: User) -> APIClient:
        api = APIClient()
        api.force_authenticate(user)
        return api

    return client


@pytest.fixture
def assigned_order(rest, client_user, reseller, manager) -> Order:
    product = ProductFactory.create(price=Decimal("50.00"), stock=5)
    response = rest(client_user).post(
        "/api/v1/orders/",
        {
            "lines": [{"product_id": product.pk, "quantity": 1}],
            "payment_method": "cash",
            "address": ADDRESS,
        },
        HTTP_IDEMPOTENCY_KEY="realtime-0001",
    )
    order = Order.objects.get(number=response.json()["number"])
    rest(manager).post(f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk})
    return order


@pytest.fixture
def thread(assigned_order) -> Conversation:
    return Conversation.objects.get(order=assigned_order)


@pytest_asyncio.fixture
async def sockets() -> AsyncIterator[list[WebsocketCommunicator]]:
    opened: list[WebsocketCommunicator] = []
    yield opened
    for socket in opened:
        await socket.disconnect()


class TestHandshake:
    async def test_requires_a_ticket(self):
        socket = WebsocketCommunicator(application, "/ws/", headers=[ORIGIN])

        connected, code = await socket.connect()

        assert connected is False
        assert code == 4401

    async def test_tickets_are_single_use(self, client_user):
        ticket = await sync_to_async(ticket_for)(client_user)
        first = WebsocketCommunicator(application, f"/ws/?ticket={ticket}", headers=[ORIGIN])
        second = WebsocketCommunicator(application, f"/ws/?ticket={ticket}", headers=[ORIGIN])

        assert (await first.connect())[0] is True
        assert (await second.connect())[0] is False
        await first.disconnect()

    async def test_foreign_origins_are_rejected(self, client_user):
        ticket = await sync_to_async(ticket_for)(client_user)
        socket = WebsocketCommunicator(
            application, f"/ws/?ticket={ticket}", headers=[(b"origin", b"https://evil.test")]
        )

        assert (await socket.connect())[0] is False

    async def test_ready_payload(self, client_user):
        ticket = await sync_to_async(ticket_for)(client_user)
        socket = WebsocketCommunicator(application, f"/ws/?ticket={ticket}", headers=[ORIGIN])
        await socket.connect()

        ready = await socket.receive_json_from()

        assert ready == {
            "type": "session.ready",
            "data": {"user_id": client_user.pk, "role": "client"},
        }
        await socket.disconnect()


class TestConversations:
    async def test_subscription_requires_access(self, client_user, thread, sockets):
        stranger = await sync_to_async(UserFactory.create)()
        own, other = await open_socket(client_user), await open_socket(stranger)
        sockets.extend([own, other])

        await own.send_json_to(
            {"type": "conversation.subscribe", "data": {"conversation_id": thread.pk}, "ref": "s1"}
        )
        await other.send_json_to(
            {"type": "conversation.subscribe", "data": {"conversation_id": thread.pk}, "ref": "s2"}
        )

        assert await own.receive_json_from() == {
            "type": "conversation.subscribed",
            "data": {"conversation_id": thread.pk},
            "ref": "s1",
        }
        denied = await other.receive_json_from()
        assert denied["type"] == "error"
        assert denied["data"]["code"] == "conversation_not_found"
        assert denied["ref"] == "s2"

    async def test_messages_sent_over_the_socket_reach_subscribers(
        self, client_user, reseller, thread, sockets
    ):
        client_socket, reseller_socket = await open_socket(client_user), await open_socket(reseller)
        sockets.extend([client_socket, reseller_socket])
        for socket in (client_socket, reseller_socket):
            await socket.send_json_to(
                {"type": "conversation.subscribe", "data": {"conversation_id": thread.pk}}
            )
            await receive_until(socket, "conversation.subscribed")

        await client_socket.send_json_to(
            {
                "type": "message.send",
                "data": {"conversation_id": thread.pk, "body": "Bonjour !", "client_msg_id": "m-1"},
                "ref": "send-1",
            }
        )

        ack = await receive_until(client_socket, "message.ack")
        created = await receive_until(reseller_socket, "message.created")
        assert ack["ref"] == "send-1"
        assert ack["data"]["client_msg_id"] == "m-1"
        assert created["data"]["message"]["id"] == ack["data"]["message_id"]
        assert created["data"]["message"]["body"] == "Bonjour !"
        assert created["data"]["message"]["sender"]["name"] == "Aline Mbuyi"

    async def test_rest_messages_are_pushed_too(self, rest, client_user, reseller, thread, sockets):
        client_socket = await open_socket(client_user)
        sockets.append(client_socket)
        await client_socket.send_json_to(
            {"type": "conversation.subscribe", "data": {"conversation_id": thread.pk}}
        )
        await receive_until(client_socket, "conversation.subscribed")

        await sync_to_async(rest(reseller).post)(
            f"/api/v1/conversations/{thread.pk}/messages/", {"body": "Livraison demain."}
        )

        created = await receive_until(client_socket, "message.created")
        updated = await receive_until(client_socket, "conversation.updated")
        assert created["data"]["message"]["body"] == "Livraison demain."
        assert updated["data"] == {"conversation_id": thread.pk}

    async def test_typing_is_relayed_to_others_only(self, client_user, reseller, thread, sockets):
        client_socket, reseller_socket = await open_socket(client_user), await open_socket(reseller)
        sockets.extend([client_socket, reseller_socket])
        for socket in (client_socket, reseller_socket):
            await socket.send_json_to(
                {"type": "conversation.subscribe", "data": {"conversation_id": thread.pk}}
            )
            await receive_until(socket, "conversation.subscribed")

        await client_socket.send_json_to(
            {"type": "typing.start", "data": {"conversation_id": thread.pk}}
        )

        typing = await receive_until(reseller_socket, "conversation.typing")
        assert typing["data"] == {
            "conversation_id": thread.pk,
            "user_id": client_user.pk,
            "name": "Aline Mbuyi",
            "typing": True,
        }
        assert await client_socket.receive_nothing(timeout=0.3)

    async def test_typing_requires_a_subscription(self, client_user, thread, sockets):
        socket = await open_socket(client_user)
        sockets.append(socket)

        await socket.send_json_to({"type": "typing.start", "data": {"conversation_id": thread.pk}})

        assert (await socket.receive_json_from())["data"]["code"] == "not_subscribed"

    async def test_read_receipts(self, client_user, reseller, thread, sockets):
        reseller_socket = await open_socket(reseller)
        client_socket = await open_socket(client_user)
        sockets.extend([reseller_socket, client_socket])
        await reseller_socket.send_json_to(
            {"type": "conversation.subscribe", "data": {"conversation_id": thread.pk}}
        )
        await receive_until(reseller_socket, "conversation.subscribed")

        await client_socket.send_json_to(
            {"type": "message.read", "data": {"conversation_id": thread.pk}}
        )

        receipt = await receive_until(reseller_socket, "conversation.read")
        counts = await receive_until(client_socket, "unread.counts")
        assert receipt["data"]["user_id"] == client_user.pk
        assert counts["data"]["conversations"] == 0


class TestPushes:
    async def test_staff_and_client_see_order_events(
        self, rest, client_user, manager, assigned_order, sockets
    ):
        manager_socket, client_socket = await open_socket(manager), await open_socket(client_user)
        sockets.extend([manager_socket, client_socket])

        await sync_to_async(rest(manager).post)(
            f"/api/v1/bo/orders/{assigned_order.pk}/transition/", {"to": "confirmed"}
        )

        staff_view = await receive_until(manager_socket, "order.status_changed")
        client_view = await receive_until(client_socket, "order.status_changed")
        notification = await receive_until(client_socket, "notification.created")
        assert staff_view["data"]["status"] == "confirmed"
        assert staff_view["data"]["previous_status"] == "assigned"
        assert client_view["data"]["number"] == assigned_order.number
        assert notification["data"]["notification"]["kind"] == "order_status"

    async def test_reseller_presence_is_broadcast_to_staff(self, manager, reseller):
        manager_socket = await open_socket(manager)

        reseller_socket = await open_socket(reseller)
        online = await receive_until(manager_socket, "presence.changed")
        await reseller_socket.disconnect()
        offline = await receive_until(manager_socket, "presence.changed")
        await manager_socket.disconnect()

        assert online["data"] == {"user_id": reseller.pk, "online": True, "availability": None}
        assert offline["data"]["online"] is False


class TestProtocolGuards:
    async def test_malformed_messages_get_errors(self, client_user, sockets):
        socket = await open_socket(client_user)
        sockets.append(socket)

        await socket.send_json_to({"type": "nope", "ref": "bad"})

        error = await socket.receive_json_from()
        assert error["data"]["code"] == "invalid_envelope"
        assert error["ref"] == "bad"

    async def test_ping_pong(self, reseller, sockets):
        socket = await open_socket(reseller)
        sockets.append(socket)

        await socket.send_json_to({"type": "presence.ping", "ref": "p"})

        assert await socket.receive_json_from() == {"type": "presence.pong", "data": {}, "ref": "p"}

    async def test_rate_limit(self, client_user, sockets, settings):
        settings.REALTIME = {"BURST": 2}
        socket = await open_socket(client_user)
        sockets.append(socket)

        for _ in range(3):
            await socket.send_json_to({"type": "presence.ping"})
        replies = [await socket.receive_json_from() for _ in range(3)]

        assert [reply["type"] for reply in replies] == ["presence.pong", "presence.pong", "error"]
        assert replies[2]["data"]["code"] == "rate_limited"
