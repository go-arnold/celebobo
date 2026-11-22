from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.audit.domain.events import RetentionApplied
from apps.audit.domain.retention import years_before
from apps.audit.services.retention import retention_rules
from apps.audit.tasks import RETENTION_TASK, apply_retention
from apps.resellers.models import ResellerApplication

pytestmark = pytest.mark.django_db

RULES = {
    "accounts.inactive_clients",
    "accounts.stale_marketing_consents",
    "messaging.stale_conversations",
    "resellers.rejected_applications",
    "content.stale_subscribers",
    "content.contact_messages",
}


@pytest.fixture
def rejected(db) -> ResellerApplication:
    return ResellerApplication.objects.create(
        first_name="Patrick",
        last_name="Kabasele",
        email="patrick@example.com",
        phone_number="+243 81 234 5678",
        city="Kinshasa",
        status="rejected",
        reviewed_at=timezone.now() - timedelta(days=400),
    )


def test_every_rule_runs_daily():
    scheduled = {
        entry["args"][0]
        for entry in settings.CELERY_BEAT_SCHEDULE.values()
        if entry["task"] == RETENTION_TASK
    }

    assert set(retention_rules) == RULES
    assert scheduled == RULES


def test_task_applies_the_rule_and_leaves_an_audit_entry(rejected, published_events):
    assert apply_retention("resellers.rejected_applications") == 1

    event = published_events.single(RetentionApplied)
    assert (event.rule, event.affected, event.actor_id) == (
        "resellers.rejected_applications",
        1,
        None,
    )
    assert not ResellerApplication.objects.filter(pk=rejected.pk).exists()


def test_runs_with_nothing_to_do_are_recorded_too(published_events):
    apply_retention("content.stale_subscribers")

    assert published_events.single(RetentionApplied).affected == 0


def test_dry_run_command_prints_and_changes_nothing(rejected, published_events):
    out = StringIO()

    call_command(
        "apply_retention", "--dry-run", "--rule", "resellers.rejected_applications", stdout=out
    )

    assert "resellers.rejected_applications" in out.getvalue()
    assert "1 à traiter" in out.getvalue()
    assert f"candidature #{rejected.pk}" in out.getvalue()
    assert ResellerApplication.objects.filter(pk=rejected.pk).exists()
    assert published_events.of_type(RetentionApplied) == []


def test_command_runs_every_rule_by_default(rejected, published_events):
    out = StringIO()

    call_command("apply_retention", stdout=out)

    assert {event.rule for event in published_events.of_type(RetentionApplied)} == RULES
    assert not ResellerApplication.objects.filter(pk=rejected.pk).exists()


def test_unknown_rule():
    with pytest.raises(CommandError, match="Règle inconnue"):
        call_command("apply_retention", "--rule", "nope")


@pytest.mark.parametrize(
    ("moment", "years", "expected"),
    [
        (datetime(2027, 3, 1, 9, tzinfo=UTC), 3, datetime(2024, 3, 1, 9, tzinfo=UTC)),
        (datetime(2028, 2, 29, 9, tzinfo=UTC), 1, datetime(2027, 2, 28, 9, tzinfo=UTC)),
    ],
)
def test_years_before(moment, years, expected):
    assert years_before(moment, years) == expected
