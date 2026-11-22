from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.audit.domain.retention import RetentionReport, years_before
from apps.audit.services.retention import retention_rules
from apps.resellers.domain.enums import ApplicationStatus
from apps.resellers.models import ResellerApplication

pytestmark = pytest.mark.django_db

RULE = "resellers.rejected_applications"
NOW = timezone.now()
CUTOFF = years_before(NOW, 1)


def apply(*, dry_run: bool = False) -> RetentionReport:
    return retention_rules.create(RULE).apply(now=NOW, dry_run=dry_run)


def application(
    status: ApplicationStatus, *, reviewed: datetime | None, received: datetime
) -> ResellerApplication:
    created = ResellerApplication.objects.create(
        first_name="Patrick",
        last_name="Kabasele",
        email=f"patrick{ResellerApplication.objects.count()}@example.com",
        phone_number="+243 81 234 5678",
        city="Kinshasa",
        status=status.value,
        reviewed_at=reviewed,
    )
    ResellerApplication.objects.filter(pk=created.pk).update(created_at=received)
    return created


def exists(row: ResellerApplication) -> bool:
    return ResellerApplication.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize(
    ("offset", "deleted"),
    [(timedelta(minutes=-1), True), (timedelta(minutes=1), False)],
    ids=["rejected-just-over-1-year", "rejected-just-under-1-year"],
)
def test_rejected_applications_go_1_year_after_the_decision(offset, deleted):
    # received long before: the period runs from the decision
    row = application(
        ApplicationStatus.REJECTED, reviewed=CUTOFF + offset, received=CUTOFF - timedelta(days=90)
    )

    assert apply().affected == int(deleted)
    assert exists(row) is not deleted


def test_without_decision_date_the_period_runs_from_reception():
    row = application(
        ApplicationStatus.REJECTED, reviewed=None, received=CUTOFF - timedelta(days=1)
    )

    assert apply().affected == 1
    assert not exists(row)


@pytest.mark.parametrize("status", [ApplicationStatus.PENDING, ApplicationStatus.APPROVED])
def test_other_applications_are_kept(status):
    old = CUTOFF - timedelta(days=400)
    row = application(
        status, reviewed=old if status is ApplicationStatus.APPROVED else None, received=old
    )

    assert apply().affected == 0
    assert exists(row)


def test_dry_run_and_idempotency():
    decided = CUTOFF - timedelta(days=2)
    row = application(ApplicationStatus.REJECTED, reviewed=decided, received=decided)

    dry = apply(dry_run=True)
    assert (dry.affected, dry.samples) == (
        1,
        (f"candidature #{row.pk} refusée le {decided:%Y-%m-%d}",),
    )
    assert exists(row)

    assert apply().affected == 1
    assert apply().affected == 0
