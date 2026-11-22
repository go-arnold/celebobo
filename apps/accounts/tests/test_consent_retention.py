"""Consents and retention together (policy, section 6): the marketing consent lapses after 3 years
without interaction, an anonymised account keeps its consent rows withdrawn as proof, and closing
an account erases the same identities as the anonymisation."""

from datetime import datetime, timedelta

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.utils import timezone

from apps.accounts.domain.events import ConsentWithdrawn
from apps.accounts.models import Consent, User
from apps.accounts.tests.factories import UserFactory
from apps.audit.domain.retention import RetentionReport, years_before
from apps.audit.services.retention import retention_rules
from apps.content.models import Subscriber
from apps.push.models import PushSubscription

pytestmark = pytest.mark.django_db

MARKETING_RULE = "accounts.stale_marketing_consents"
NOW = timezone.now()
LONG_AGO = years_before(NOW, 3) - timedelta(days=30)


def apply(rule: str, *, dry_run: bool = False) -> RetentionReport:
    return retention_rules.create(rule).apply(now=NOW, dry_run=dry_run)


def subscriber(email: str) -> Subscriber:
    return Subscriber.objects.create(email=email, source="compte")


def with_marketing(user: User, *, given: datetime = LONG_AGO, seen: datetime = LONG_AGO) -> User:
    Consent.objects.create(user=user, kind="marketing", version="0.9.2", source="account")
    Consent.objects.filter(user=user).update(accepted_at=given)
    User.objects.filter(pk=user.pk).update(date_joined=given, last_login=seen, last_seen_at=seen)
    subscriber(user.email)
    user.refresh_from_db()
    return user


def marketing_open(user: User) -> bool:
    return Consent.objects.filter(user=user, kind="marketing", withdrawn_at__isnull=True).exists()


class TestMarketingConsentLapses:
    def test_withdrawn_after_three_years_without_interaction(self, published_events):
        user = with_marketing(UserFactory.create(email="kito@celebobo.test"))

        report = apply(MARKETING_RULE)

        assert report.affected == 1
        assert not marketing_open(user)
        # the row stays, as proof, and the newsletter follows
        assert Consent.objects.filter(user=user, kind="marketing").count() == 1
        assert Subscriber.objects.get(email=user.email).unsubscribed_at is not None
        withdrawn = published_events.of_type(ConsentWithdrawn)
        assert [(e.user_id, e.kind.value, e.actor_id) for e in withdrawn] == [
            (user.pk, "marketing", None)
        ]
        # the other consents and the account are untouched
        assert Consent.objects.filter(user=user, withdrawn_at__isnull=True).count() == 2
        user.refresh_from_db()
        assert user.deleted_at is None

    def test_a_recent_login_is_an_interaction(self):
        user = with_marketing(UserFactory.create(), seen=NOW - timedelta(days=10))

        assert apply(MARKETING_RULE).affected == 0
        assert marketing_open(user)

    def test_giving_it_again_restarts_the_period(self):
        user = with_marketing(UserFactory.create(), given=NOW - timedelta(days=10))

        assert apply(MARKETING_RULE).affected == 0
        assert marketing_open(user)

    def test_a_newer_acceptance_on_another_version_counts(self):
        user = with_marketing(UserFactory.create())
        Consent.objects.create(user=user, kind="marketing", version="1.0", source="account")

        assert apply(MARKETING_RULE).affected == 0
        assert (
            Consent.objects.filter(user=user, kind="marketing", withdrawn_at__isnull=True).count()
            == 2
        )

    def test_dry_run_changes_nothing(self):
        user = with_marketing(UserFactory.create())

        report = apply(MARKETING_RULE, dry_run=True)

        assert report.affected == 1
        assert marketing_open(user)

    def test_it_runs_every_day(self, settings):
        entry = settings.CELERY_BEAT_SCHEDULE[f"retention-{MARKETING_RULE}"]
        assert entry["args"] == (MARKETING_RULE,)


def test_an_anonymised_account_keeps_its_consents_withdrawn():
    user = with_marketing(UserFactory.create(email="sleeper@celebobo.test"))
    email = user.email

    assert apply("accounts.inactive_clients").affected == 1

    assert Consent.objects.filter(user=user).count() == 3
    assert not Consent.objects.filter(user=user, withdrawn_at__isnull=True).exists()
    # the subscription went with the identity scrub: the real address is not kept as an opposition
    assert not Subscriber.objects.filter(email=email).exists()


def test_closing_an_account_erases_the_same_identities(api):
    user = UserFactory.create()
    EmailAddress.objects.get_or_create(user=user, email=user.email)
    SocialAccount.objects.create(user=user, provider="google", uid="g-2")
    PushSubscription.objects.create(user=user, endpoint="https://push.test/2", p256dh="k", auth="a")
    api.force_authenticate(user)

    response = api.delete("/api/v1/me/")

    assert response.status_code == 204, response.content
    assert not EmailAddress.objects.filter(user=user).exists()
    assert not SocialAccount.objects.filter(user=user).exists()
    assert not PushSubscription.objects.filter(user=user).exists()
