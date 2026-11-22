from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.audit.domain.retention import RetentionReport, years_before
from apps.audit.services.retention import retention_rules
from apps.messaging.models import Conversation, Message, Notification
from apps.messaging.tests.conftest import thread_of
from apps.orders.models import Order

pytestmark = pytest.mark.django_db(transaction=True)

RULE = "messaging.stale_conversations"
NOW = timezone.now()
CUTOFF = years_before(NOW, 3)
LONG_AGO = CUTOFF - timedelta(days=30)


def apply(*, dry_run: bool = False) -> RetentionReport:
    return retention_rules.create(RULE).apply(now=NOW, dry_run=dry_run)


def aged(order: Order, *, ordered: datetime, last_message: datetime | None) -> Conversation:
    Order.objects.filter(pk=order.pk).update(created_at=ordered)
    thread: Conversation = thread_of(order)
    Conversation.objects.filter(pk=thread.pk).update(
        created_at=ordered, last_message_at=last_message
    )
    return thread


def exists(thread: Conversation) -> bool:
    return Conversation.objects.filter(pk=thread.pk).exists()


def test_old_order_thread_goes_with_its_messages(client_user, place_order):
    thread = aged(place_order(client_user), ordered=LONG_AGO, last_message=LONG_AGO)
    Message.objects.create(conversation=thread, sender=client_user, body="Merci")
    Notification.objects.create(
        recipient=client_user, kind="new_message", title="t", body="b", conversation=thread
    )

    assert apply().affected == 1
    assert not exists(thread)
    assert not Message.objects.filter(conversation_id=thread.pk).exists()
    assert not Notification.objects.filter(conversation_id=thread.pk).exists()


@pytest.mark.parametrize(
    ("offset", "deleted"),
    [(timedelta(minutes=-1), True), (timedelta(minutes=1), False)],
    ids=["last-message-just-over-3-years", "last-message-just-under-3-years"],
)
def test_last_message_threshold(client_user, place_order, offset, deleted):
    thread = aged(place_order(client_user), ordered=LONG_AGO, last_message=CUTOFF + offset)

    apply()

    assert exists(thread) is not deleted


def test_a_recent_order_keeps_the_client_s_old_threads(client_user, place_order):
    old = aged(place_order(client_user), ordered=LONG_AGO, last_message=LONG_AGO)
    recent = place_order(client_user)

    assert apply().affected == 0
    assert exists(old)
    assert exists(thread_of(recent))


def test_order_just_over_3_years_no_longer_keeps_them(client_user, place_order):
    old = aged(place_order(client_user), ordered=LONG_AGO, last_message=LONG_AGO)
    other = place_order(client_user)
    aged(other, ordered=CUTOFF - timedelta(minutes=1), last_message=None)

    assert apply().affected == 2
    assert not exists(old)


def test_support_thread_without_order_or_message(client_user):
    thread = Conversation.objects.create(kind="support", client=client_user, subject="Aide")
    Conversation.objects.filter(pk=thread.pk).update(created_at=LONG_AGO)

    assert apply().affected == 1
    assert not exists(thread)


def test_dry_run_and_idempotency(client_user, place_order):
    thread = aged(place_order(client_user), ordered=LONG_AGO, last_message=LONG_AGO)

    dry = apply(dry_run=True)
    assert (dry.affected, dry.samples) == (
        1,
        (f"discussion #{thread.pk}, dernière activité le {LONG_AGO:%Y-%m-%d}",),
    )
    assert exists(thread)

    assert apply().affected == 1
    assert apply().affected == 0
