import pytest

from apps.realtime.adapters.channels import CachePresenceStore
from apps.realtime.domain.groups import conversation_group, user_group
from apps.realtime.domain.protocol import (
    ClientMessage,
    Envelope,
    InvalidEnvelope,
    ServerEvent,
    outbound,
)
from apps.realtime.domain.rate_limit import TokenBucket
from apps.realtime.services.presence import PresenceService


class TestEnvelope:
    def test_parses_valid_messages(self):
        envelope = Envelope.parse(
            {"type": "message.send", "data": {"conversation_id": 4, "body": "Salut"}, "ref": "r1"}
        )

        assert envelope.type is ClientMessage.SEND
        assert envelope.integer("conversation_id") == 4
        assert envelope.text("body", limit=10) == "Salut"
        assert envelope.ref == "r1"

    @pytest.mark.parametrize(
        "raw",
        [
            "not a dict",
            {"type": "unknown.kind"},
            {"type": "presence.ping", "data": []},
            {"type": "presence.ping", "ref": 12},
            {"type": "presence.ping", "ref": "x" * 65},
        ],
    )
    def test_rejects_malformed_messages(self, raw):
        with pytest.raises(InvalidEnvelope):
            Envelope.parse(raw)

    @pytest.mark.parametrize("value", [None, "4", True, 0, -3])
    def test_integer_fields_are_strict(self, value):
        with pytest.raises(InvalidEnvelope):
            Envelope(type=ClientMessage.SUBSCRIBE, data={"conversation_id": value}).integer(
                "conversation_id"
            )

    def test_text_fields_have_limits(self):
        with pytest.raises(InvalidEnvelope):
            Envelope(type=ClientMessage.SEND, data={"body": "x" * 11}).text("body", limit=10)

    def test_outbound_shape(self):
        assert outbound(ServerEvent.PONG, {}, ref="r") == {
            "type": "presence.pong",
            "data": {},
            "ref": "r",
        }
        assert outbound(ServerEvent.PONG, {}) == {"type": "presence.pong", "data": {}}

    def test_group_names(self):
        assert user_group(3) == "user.3"
        assert conversation_group(9) == "conversation.9"


class TestTokenBucket:
    def test_bursts_then_refills(self):
        bucket = TokenBucket(capacity=3, refill_per_second=1.0)

        assert [bucket.allow(100.0) for _ in range(4)] == [True, True, True, False]
        assert bucket.allow(100.5) is False
        assert bucket.allow(101.1) is True


class TestPresence:
    def test_counts_connections_per_user(self):
        presence = PresenceService(CachePresenceStore(), ttl=60)

        assert presence.connected(5) is True
        assert presence.connected(5) is False
        assert presence.online([5, 6]) == {5}
        assert presence.disconnected(5) is False
        assert presence.disconnected(5) is True
        assert presence.online([5]) == set()

    def test_heartbeat_revives_expired_presence(self):
        presence = PresenceService(CachePresenceStore(), ttl=60)

        presence.heartbeat(8)

        assert presence.online([8]) == {8}

    def test_disconnect_without_connect_is_offline(self):
        assert PresenceService(CachePresenceStore()).disconnected(42) is True
