from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.audit.domain.retention import RetentionReport, years_before
from apps.audit.services.retention import retention_rules
from apps.content.models import ContactMessage, Subscriber
from apps.content.repositories import SubscriberRepository
from apps.content.services.newsletter import NewsletterService

pytestmark = pytest.mark.django_db

RULE = "content.stale_subscribers"
NOW = timezone.now()
CUTOFF = years_before(NOW, 3)


def apply(*, dry_run: bool = False) -> RetentionReport:
    return retention_rules.create(RULE).apply(now=NOW, dry_run=dry_run)


def subscriber(email: str, *, since: datetime, unsubscribed: bool = False) -> Subscriber:
    created = Subscriber.objects.create(email=email)
    Subscriber.objects.filter(pk=created.pk).update(
        subscribed_at=since, unsubscribed_at=since if unsubscribed else None
    )
    return created


@pytest.mark.parametrize(
    ("offset", "deleted"),
    [(timedelta(minutes=-1), True), (timedelta(minutes=1), False)],
    ids=["just-after-3-years", "just-before-3-years"],
)
def test_subscribers_without_interaction_for_3_years_are_deleted(offset, deleted):
    row = subscriber("grace@example.com", since=CUTOFF + offset)

    report = apply()

    assert report.affected == int(deleted)
    assert Subscriber.objects.filter(pk=row.pk).exists() is not deleted


def test_unsubscribed_addresses_stay_on_the_opposition_list():
    row = subscriber("grace@example.com", since=CUTOFF - timedelta(days=400), unsubscribed=True)

    assert apply().affected == 0
    assert Subscriber.objects.filter(pk=row.pk).exists()


def test_account_subscriptions_follow_the_marketing_consent_instead():
    row = subscriber("client@example.com", since=CUTOFF - timedelta(days=400))
    Subscriber.objects.filter(pk=row.pk).update(source="compte")

    # the account's marketing consent has its own 3-year rule, counting the account's activity
    assert apply().affected == 0
    assert Subscriber.objects.filter(pk=row.pk).exists()


def test_subscribing_again_restarts_the_period():
    row = subscriber("grace@example.com", since=CUTOFF - timedelta(days=1), unsubscribed=True)

    NewsletterService(SubscriberRepository(), clock=lambda: NOW).subscribe(
        "grace@example.com", source="footer"
    )

    assert apply().affected == 0
    row.refresh_from_db()
    assert row.subscribed_at == NOW


def test_dry_run_and_idempotency():
    row = subscriber("grace@example.com", since=CUTOFF - timedelta(days=1))

    dry = apply(dry_run=True)
    assert (dry.affected, dry.samples) == (
        1,
        (f"abonné #{row.pk} inscrit le {CUTOFF - timedelta(days=1):%Y-%m-%d}",),
    )
    assert Subscriber.objects.filter(pk=row.pk).exists()

    assert apply().affected == 1
    assert apply().affected == 0


CONTACT_RULE = "content.contact_messages"


def contact_message(*, received: datetime) -> ContactMessage:
    created = ContactMessage.objects.create(
        name="Grace Ilunga",
        email="grace@example.com",
        phone="+243 81 000 0002",
        subject="order",
        message="Où en est ma commande ?",
    )
    ContactMessage.objects.filter(pk=created.pk).update(created_at=received)
    return created


@pytest.mark.parametrize(
    ("offset", "deleted"),
    [(timedelta(minutes=-1), True), (timedelta(minutes=1), False)],
    ids=["received-just-over-3-years", "received-just-under-3-years"],
)
def test_contact_messages_go_3_years_after_receipt(offset, deleted):
    row = contact_message(received=CUTOFF + offset)

    report = retention_rules.create(CONTACT_RULE).apply(now=NOW, dry_run=False)

    assert report.affected == int(deleted)
    assert ContactMessage.objects.filter(pk=row.pk).exists() is not deleted


def test_contact_messages_dry_run_and_idempotency():
    received = CUTOFF - timedelta(days=1)
    row = contact_message(received=received)
    rule = retention_rules.create(CONTACT_RULE)

    dry = rule.apply(now=NOW, dry_run=True)
    assert (dry.affected, dry.samples) == (
        1,
        (f"message de contact #{row.pk} reçu le {received:%Y-%m-%d}",),
    )
    assert ContactMessage.objects.filter(pk=row.pk).exists()

    assert rule.apply(now=NOW, dry_run=False).affected == 1
    assert rule.apply(now=NOW, dry_run=False).affected == 0
