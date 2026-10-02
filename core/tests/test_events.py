from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import override_settings
from structlog.testing import capture_logs

from core.events.base import DomainEvent
from core.events.bus import EventBus
from core.events.codec import decode, encode
from core.events.dispatchers import CeleryDispatcher, InlineDispatcher, configured_dispatcher
from core.tests import events
from core.tests.events import Channel, OrderPlaced, PriorityOrderPlaced


def make_order(**overrides) -> OrderPlaced:
    values = {
        "order_id": 12,
        "total": Decimal("749.00"),
        "channel": Channel.WEB,
        "actor_id": 3,
        "delivery_date": date(2026, 10, 4),
        "item_ids": (1, 2),
        "labels": {"zone": "Gombe"},
    }
    return OrderPlaced(**{**values, **overrides})


@pytest.fixture
def bus() -> EventBus:
    return EventBus(dispatcher=InlineDispatcher)


@pytest.fixture(autouse=True)
def _reset_received():
    events.received.clear()
    yield
    events.received.clear()


class TestCodec:
    def test_round_trip_preserves_types(self):
        event = make_order()

        restored = decode(OrderPlaced, encode(event))

        assert restored == event
        assert isinstance(restored.total, Decimal)
        assert restored.channel is Channel.WEB
        assert restored.item_ids == (1, 2)

    def test_payload_is_json_compatible(self):
        payload = encode(make_order(delivery_date=None, labels=None))

        assert payload["total"] == "749.00"
        assert payload["channel"] == "web"
        assert payload["delivery_date"] is None
        assert isinstance(payload["event_id"], str)

    def test_rejects_unsupported_values(self):
        with pytest.raises(TypeError, match="Cannot encode"):
            encode(make_order(labels={"x": object()}))

    def test_event_name_is_importable_path(self):
        assert OrderPlaced.event_name() == "core.tests.events.OrderPlaced"


class TestEventBus:
    @pytest.mark.django_db
    def test_publish_waits_for_commit(self, bus, django_capture_on_commit_callbacks):
        handler = Mock()
        bus.subscribe(handler, OrderPlaced)

        with django_capture_on_commit_callbacks() as callbacks:
            bus.publish(make_order())
            handler.assert_not_called()

        assert len(callbacks) == 1
        callbacks[0]()
        handler.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    def test_rolled_back_transaction_drops_events(self, bus):
        handler = Mock()
        bus.subscribe(handler, OrderPlaced)

        def place_then_fail():
            with transaction.atomic():
                bus.publish(make_order())
                raise RuntimeError

        with pytest.raises(RuntimeError):
            place_then_fail()

        handler.assert_not_called()

    def test_observers_of_base_classes_receive_subtypes(self, bus):
        every_event, orders, priority = Mock(), Mock(), Mock()
        bus.subscribe(every_event, DomainEvent)
        bus.subscribe(orders, OrderPlaced)
        bus.subscribe(priority, PriorityOrderPlaced)

        bus.dispatch(PriorityOrderPlaced(order_id=1, total=Decimal(1), channel=Channel.WEB))
        bus.dispatch(make_order())

        assert every_event.call_count == 2
        assert orders.call_count == 2
        assert priority.call_count == 1

    def test_failing_handler_is_isolated(self, bus):
        healthy = Mock()
        bus.subscribe(Mock(side_effect=RuntimeError("boom")), OrderPlaced)
        bus.subscribe(healthy, OrderPlaced)

        with capture_logs() as logs:
            bus.dispatch(make_order())

        healthy.assert_called_once()
        assert any(log["event"] == "event.handler_failed" for log in logs)

    def test_decorator_subscription_is_idempotent(self, bus):
        calls = []

        @bus.on(OrderPlaced)
        def handler(event):
            calls.append(event)

        bus.subscribe(handler, OrderPlaced)
        bus.dispatch(make_order())

        assert len(calls) == 1

    def test_on_requires_event_types(self, bus):
        with pytest.raises(ValueError, match="at least one"):
            bus.on()

    def test_background_handlers_run_through_the_codec(self, bus):
        bus.subscribe(events.record_in_background, OrderPlaced, background=True)
        event = make_order()

        bus.dispatch(event)

        assert events.received == [event]
        assert events.received[0] is not event

    def test_background_handlers_are_deduplicated_per_event(self, bus):
        bus.subscribe(events.record_in_background, OrderPlaced, background=True)
        event = make_order()

        bus.dispatch(event)
        bus.dispatch(event)

        assert len(events.received) == 1

    def test_background_handlers_must_be_importable(self, bus):
        def local_handler(event):
            return None

        with pytest.raises(ImproperlyConfigured, match="module-level"):
            bus.subscribe(local_handler, OrderPlaced, background=True)

    def test_subscribers_lists_inline_and_background(self, bus):
        bus.subscribe(events.record_in_background, OrderPlaced, background=True)

        assert bus.subscribers(OrderPlaced) == ("core.tests.events.record_in_background",)

        bus.clear()
        assert bus.subscribers(OrderPlaced) == ()


class TestDispatchers:
    @override_settings(CORE={"EVENTS_DISPATCHER": "celery"})
    def test_dispatcher_follows_settings(self):
        assert isinstance(configured_dispatcher(), CeleryDispatcher)

    def test_celery_dispatcher_executes_task(self):
        CeleryDispatcher().enqueue("core.tests.events.record_in_background", make_order())

        assert len(events.received) == 1
