from datetime import timedelta

import pytest
from auditlog.models import LogEntry
from django.utils import timezone

from apps.audit.facades import AuditFacade
from apps.resellers.models import ResellerApplication
from core.container import container

pytestmark = pytest.mark.django_db

LOGS = "/api/v1/bo/audit-logs/"


@pytest.fixture
def repriced(as_user, manager, phone):
    response = as_user(manager).patch(
        f"/api/v1/bo/products/{phone.pk}/", {"price": "130.00"}, format="json"
    )
    assert response.status_code == 200, response.json()
    return LogEntry.objects.filter(object_pk=str(phone.pk), action=LogEntry.Action.UPDATE).latest(
        "timestamp"
    )


def test_api_changes_are_attributed_to_the_authenticated_user(as_user, admin, manager, repriced):
    body = as_user(admin).get(LOGS, {"object_type": "catalog.product", "action": "update"}).json()

    entry = body["results"][0]
    assert entry["actor"] == {"id": manager.pk, "name": "Joël Mpiana"}
    assert entry["changes"]["price"] == ["120.00", "130.00"]
    assert entry["object_repr"] == "Galaxy A55"
    assert entry["remote_addr"] == "127.0.0.1"
    assert "updated_at" not in entry["changes"]
    assert "search_vector" not in entry["changes"]


def test_filters(as_user, admin, manager, repriced):
    api = as_user(admin)
    today = timezone.localdate().isoformat()

    assert api.get(LOGS, {"actor_id": manager.pk}).json()["meta"]["count"] >= 1
    assert api.get(LOGS, {"actor_id": admin.pk}).json()["meta"]["count"] == 0
    assert api.get(LOGS, {"date": today, "search": "galaxy"}).json()["meta"]["count"] >= 1
    assert api.get(LOGS, {"date": "2000-01-01"}).json()["meta"]["count"] == 0
    assert api.get(LOGS, {"object_type": "orders.order"}).json()["meta"]["count"] == 0
    assert api.get(LOGS, {"object_type": "nope"}).status_code == 400


def test_detail(as_user, admin, repriced):
    body = as_user(admin).get(f"{LOGS}{repriced.pk}/").json()

    assert body["action"] == "update"
    assert body["object_type"] == "catalog.product"
    assert as_user(admin).get(f"{LOGS}999999/").status_code == 404


def test_password_changes_are_never_logged(as_user, admin, manager):
    manager.set_password("N0uveau-mot-de-passe!")
    manager.save()

    entries = LogEntry.objects.filter(object_pk=str(manager.pk))
    assert all("password" not in (entry.changes or {}) for entry in entries)


def test_anonymous_changes_have_no_actor(api, as_user, admin):
    api.post(
        "/api/v1/reseller-applications/",
        {
            "first_name": "Grâce",
            "last_name": "Ilunga",
            "email": "grace@example.com",
            "phone_number": "+243 82 555 0101",
            "city": "Kolwezi",
        },
        format="json",
    )
    application = ResellerApplication.objects.get()

    body = as_user(admin).get(LOGS, {"object_type": "resellers.resellerapplication"}).json()

    assert body["results"][0]["object_id"] == str(application.pk)
    assert body["results"][0]["actor"] is None


def test_tracked_types(as_user, admin):
    keys = {row["key"] for row in as_user(admin).get(f"{LOGS}object-types/").json()}

    assert {"accounts.user", "catalog.product", "orders.order", "sales.sale"} <= keys


def test_only_admins_read_the_audit_trail(as_user, manager):
    assert as_user(manager).get(LOGS).status_code == 403


def test_purge(repriced):
    LogEntry.objects.update(timestamp=timezone.now() - timedelta(days=400))

    assert container.resolve(AuditFacade).purge()["changes"] >= 1
    assert not LogEntry.objects.exists()
