from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analytics.domain.events import SalesFactsRefreshed
from apps.audit.facades import AuditFacade
from apps.audit.models import EventRecord
from apps.audit.tasks import purge_audit_trail
from apps.catalog.domain.events import ProductChanged
from core.container import container

pytestmark = pytest.mark.django_db

EVENTS = "/api/v1/bo/audit-logs/events/"


def test_domain_events_are_recorded_with_actor_and_payload(
    as_user, admin, manager, phone, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        as_user(manager).patch(
            f"/api/v1/bo/products/{phone.pk}/", {"price": "99.00"}, format="json"
        )

    body = as_user(admin).get(EVENTS, {"event_type": "ProductChanged"}).json()

    (entry,) = body["results"]
    assert entry["name"] == "ProductChanged"
    assert entry["event_type"] == "apps.catalog.domain.events.ProductChanged"
    assert entry["actor"]["id"] == manager.pk
    assert entry["payload"] == {"product_id": phone.pk}
    assert "apps.catalog.domain.events.ProductChanged" in body["meta"]["event_types"]


def test_recording_is_idempotent_and_skips_noise():
    audit = container.resolve(AuditFacade)
    event = ProductChanged(product_id=7, actor_id=None)

    assert audit.record(event) is True
    assert audit.record(event) is False
    assert audit.record(SalesFactsRefreshed()) is False
    assert EventRecord.objects.count() == 1


def test_filters(as_user, admin, manager):
    audit = container.resolve(AuditFacade)
    audit.record(ProductChanged(product_id=1, actor_id=manager.pk))
    audit.record(ProductChanged(product_id=2, actor_id=None))
    api = as_user(admin)

    assert api.get(EVENTS, {"actor_id": manager.pk}).json()["meta"]["count"] == 1
    assert api.get(EVENTS, {"date": timezone.localdate().isoformat()}).json()["meta"]["count"] == 2
    assert api.get(EVENTS, {"date_from": "2026-02-01", "date_to": "2026-01-01"}).status_code == 400


def test_purge_task():
    audit = container.resolve(AuditFacade)
    audit.record(ProductChanged(product_id=1, occurred_at=timezone.now() - timedelta(days=400)))
    audit.record(ProductChanged(product_id=2))

    assert purge_audit_trail()["events"] == 1
    assert EventRecord.objects.count() == 1
