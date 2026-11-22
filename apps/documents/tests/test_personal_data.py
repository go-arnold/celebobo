import io
import json
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Address
from apps.accounts.tests.factories import ResellerFactory, UserFactory
from apps.audit.models import EventRecord
from apps.catalog.models import Favorite
from apps.catalog.tests.factories import ReviewFactory
from apps.documents.domain.enums import JobKind
from apps.documents.facades import DocumentJobFacade
from apps.documents.models import Job
from apps.documents.providers import register_generators
from apps.documents.services.generators import generator_registry
from apps.loyalty.models import PointsEntry
from apps.messaging.models import Conversation, Message
from apps.orders.models import Order
from apps.sales.domain.payouts import PayoutCalendar
from apps.sales.facades import CommissionFacade
from apps.sales.models import CommissionEntry
from core.container import container

pytestmark = pytest.mark.django_db

EXPORT = "/api/v1/me/data-export/"
CLIENT_SECTIONS = [
    "account",
    "notification_preferences",
    "orders",
    "points",
    "reviews",
    "favorites",
    "messages",
    "reseller_applications",
]


class Exploding:
    def run(self, request):
        raise RuntimeError("boom")


@pytest.fixture
def exploding_export():
    generator_registry.add(JobKind.PERSONAL_DATA.value, Exploding, replace=True)
    yield
    register_generators(container)


def export(api, run_jobs) -> dict[str, Any]:
    with run_jobs():
        response = api.post(EXPORT)
    assert response.status_code == 202, response.json()
    body: dict[str, Any] = response.json()
    return body


def unzip(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def download(api, run_jobs) -> tuple[dict[str, Any], str, str]:
    job_id = export(api, run_jobs)["id"]
    response = api.get(f"{EXPORT}{job_id}/download/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "attachment" in response["Content-Disposition"]
    files = unzip(response.content)
    raw = files["mes-donnees.json"].decode()
    return json.loads(raw), raw, files["mes-donnees.html"].decode()


@pytest.fixture
def delivered(
    as_user, shopper, phone, place_order, *, manager, reseller, run_jobs, renderer
) -> Order:
    reseller.phone_number = "+243 99 777 0000"
    reseller.save(update_fields=["phone_number"])
    order = Order.objects.get(number=place_order(shopper, phone, quantity=2)["number"])
    api = as_user(manager)
    with run_jobs():
        assigned = api.post(f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk})
        assert assigned.status_code == 200, assigned.json()
        response = api.post(
            f"/api/v1/bo/orders/{order.pk}/transition/",
            {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
        )
    assert response.status_code == 200, response.json()
    return order


@pytest.fixture
def refunded(as_user, shopper, phone, place_order) -> Order:
    order = Order.objects.get(number=place_order(shopper, phone)["number"])
    as_user(shopper).post(f"/api/v1/me/orders/{order.number}/cancel/", {"reason": "changed_mind"})
    Order.objects.filter(pk=order.pk).update(
        refund_due=Decimal("120.00"), refunded_at=timezone.now(), refund_note="Remboursé M-Pesa"
    )
    return order


@pytest.fixture
def client_history(shopper, manager, phone, *, delivered, refunded) -> None:
    Address.objects.create(
        user=shopper,
        recipient="Aline Mbuyi",
        phone="+243 81 000 0001",
        line1="Av. Lumumba n°12",
        quarter="Ibanda",
        city="Bukavu",
        country="RD Congo",
        is_default=True,
    )
    PointsEntry.objects.create(
        user=shopper,
        kind="earn",
        amount=Decimal("3.60"),
        remaining=Decimal("3.60"),
        available_at=timezone.now() - timedelta(days=1),
    )
    ReviewFactory.create(user=shopper, product=phone, message="Très bon <script>x</script>")
    Favorite.objects.create(user=shopper, product=phone)
    support = Conversation.objects.create(kind="support", client=shopper, subject="Garantie")
    Message.objects.create(conversation=support, sender=shopper, body="Mon écran clignote")
    Message.objects.create(conversation=support, sender=manager, body="Apportez-le en boutique")
    # someone else's data, never exported
    other = UserFactory.create(email="autre@celebobo.test", first_name="Bernard")
    ReviewFactory.create(user=other, product=phone, message="Avis d'un autre client")
    Conversation.objects.create(kind="support", client=other, subject="Autre sujet")


@pytest.mark.usefixtures("client_history")
class TestClientExport:
    def test_runs_in_the_background_and_reports_its_status(self, as_user, shopper, run_jobs):
        api = as_user(shopper)
        assert api.get(EXPORT).json() == {"job": None, "available_at": None}

        job = export(api, run_jobs)

        assert job["kind"] == "personal_data"
        assert job["format"] == "zip"
        status = api.get(EXPORT).json()
        assert status["job"]["status"] == "done"
        assert status["job"]["downloadable"] is True
        assert status["job"]["expired"] is False
        assert status["job"]["filename"].startswith("celebobo-mes-donnees-")
        assert status["job"]["summary"]["sections"]["orders"] == 2
        assert status["available_at"] is not None
        finished = Job.objects.get().finished_at
        assert finished is not None
        expires_at = datetime.fromisoformat(status["job"]["expires_at"])
        assert abs(expires_at - (finished + timedelta(hours=48))) < timedelta(seconds=1)

    def test_zip_holds_json_html_and_a_readme(self, as_user, shopper, run_jobs):
        api = as_user(shopper)
        job_id = export(api, run_jobs)["id"]

        files = unzip(api.get(f"{EXPORT}{job_id}/download/").content)

        assert sorted(files) == ["LISEZMOI.txt", "mes-donnees.html", "mes-donnees.json"]
        assert "30 jours" in files["LISEZMOI.txt"].decode()

    def test_json_layout_is_stable(self, as_user, shopper, run_jobs):
        document, _, _ = download(as_user(shopper), run_jobs)

        assert list(document) == ["format", "version", "generated_at", "user_id", "data"]
        assert document["format"] == "celebobo.personal-data"
        assert document["version"] == 1
        assert document["user_id"] == shopper.pk
        assert list(document["data"]) == CLIENT_SECTIONS
        assert list(document["data"]["account"]) == [
            "id",
            "email",
            "email_verified",
            "first_name",
            "last_name",
            "phone_number",
            "avatar",
            "role",
            "date_joined",
            "last_login",
            "referral_code",
            "invited_by",
            "invited_at",
            "addresses",
        ]
        order = document["data"]["orders"][0]
        assert list(order) == [
            "number",
            "status",
            "created_at",
            "items",
            "subtotal",
            "discount",
            "coupon_code",
            "points",
            "shipping_fee",
            "total",
            "points_earned",
            "payment_method",
            "delivery",
            "note",
            "reseller",
            "refund",
            "cancel_reason",
            "history",
            "rating",
            "documents",
        ]
        assert list(order["items"][0]) == [
            "product",
            "variant",
            "sku",
            "quantity",
            "unit_price",
            "total",
            "discount",
            "points",
            "amount_paid",
            "returned_quantity",
            "returned_amount",
        ]

    def test_account_orders_and_payments(self, as_user, shopper, delivered, refunded, run_jobs):
        document, _, _ = download(as_user(shopper), run_jobs)
        data = document["data"]

        account = data["account"]
        assert account["email"] == "aline@celebobo.test"
        assert account["phone_number"] == "+243 81 000 0001"
        assert account["role"] == "client"
        assert account["addresses"][0]["line1"] == "Av. Lumumba n°12"
        assert data["notification_preferences"]["promotions"] == {"email": True, "push": False}
        orders = {order["number"]: order for order in data["orders"]}
        done = orders[delivered.number]
        assert done["status"] == "delivered"
        assert done["total"] == f"{delivered.total:.2f}"
        assert done["items"][0] == {
            "product": "Galaxy A55",
            "variant": "",
            "sku": done["items"][0]["sku"],
            "quantity": 2,
            "unit_price": "120.00",
            "total": "240.00",
            "discount": "0.00",
            "points": "0.00",
            "amount_paid": "240.00",
            "returned_quantity": 0,
            "returned_amount": "0.00",
        }
        assert done["payment_method"] == "orange_money"
        assert done["delivery"]["address"]["recipient"] == "Aline Mbuyi"
        assert done["reseller"] == {"name": "Patrick Kabasele"}
        assert done["documents"]["invoice"] == f"facture-{delivered.number}.pdf"
        assert done["documents"]["delivery_receipt"]["number"] == f"R-{delivered.number}"
        assert [entry["status"] for entry in done["history"]][-1] == "delivered"
        assert done["created_at"].endswith("+00:00")
        cancelled = orders[refunded.number]
        assert cancelled["status"] == "cancelled"
        assert cancelled["documents"] == {"invoice": None, "delivery_receipt": None}
        assert cancelled["refund"]["refund_due"] == "120.00"
        assert cancelled["refund"]["note"] == "Remboursé M-Pesa"
        assert cancelled["refund"]["refunded_at"] is not None

    def test_points_reviews_favorites_and_messages(self, as_user, shopper, run_jobs):
        document, _, _ = download(as_user(shopper), run_jobs)
        data = document["data"]

        assert data["points"]["balance"]["available"] == "3.60"
        assert {movement["kind"] for movement in data["points"]["movements"]} >= {"earn"}
        assert all(isinstance(m["amount"], str) for m in data["points"]["movements"])
        assert data["reviews"] == [
            {
                "product": "Galaxy A55",
                "rating": 5,
                "message": "Très bon <script>x</script>",
                "verified": True,
                "moderation": "published",
                "created_at": data["reviews"][0]["created_at"],
            }
        ]
        assert data["favorites"][0]["product"] == "Galaxy A55"
        support = next(t for t in data["messages"]["threads"] if t["subject"] == "Garantie")
        assert support["own_messages_only"] is False
        assert [message["body"] for message in support["messages"]] == [
            "Mon écran clignote",
            "Apportez-le en boutique",
        ]
        assert data["messages"]["truncated"] is False
        assert data["reseller_applications"] == []

    def test_leaves_out_other_peoples_data(self, as_user, shopper, run_jobs):
        _, raw, html = download(as_user(shopper), run_jobs)

        for text in ("autre@celebobo.test", "Avis d'un autre client", "Autre sujet", "Bernard"):
            assert text not in raw
            assert text not in html
        # the reseller's name only: never their phone or e-mail
        assert "+243 99 777 0000" not in raw
        assert "@" not in raw.replace("aline@celebobo.test", "")
        assert "delivery_code" not in raw

    def test_html_page_is_french_and_escaped(self, as_user, shopper, run_jobs):
        _, _, html = download(as_user(shopper), run_jobs)

        assert '<html lang="fr">' in html
        assert "Commandes" in html
        assert "Livrée" in html
        assert "Orange Money" in html
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;x&lt;/script&gt;" in html


class TestResellerExport:
    @pytest.fixture
    def activity(self, as_user, admin, reseller, phone, sell) -> None:
        CommissionEntry.objects.create(
            reseller=reseller,
            kind="earned",
            rule="paid",
            base_amount=Decimal("100.00"),
            amount=Decimal("10.00"),
            available_at=timezone.now() - timedelta(days=3),
        )
        payout_date = PayoutCalendar().next(timezone.localdate())
        assert container.resolve(CommissionFacade).prepare_statements(payout_date) == 1
        statement_id = as_user(admin).get("/api/v1/bo/payout-statements/").json()["results"][0]
        response = as_user(admin).post(
            "/api/v1/bo/payouts/",
            {"statement_id": statement_id["id"], "note": "M-Pesa"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="payout-export-1",
        )
        assert response.status_code == 201, response.json()
        # a sale after the payout: its commission is still pending
        sell(reseller, phone)

    @pytest.mark.usefixtures("activity")
    def test_sales_commissions_statements_and_payouts(self, as_user, reseller, run_jobs):
        document, raw, html = download(as_user(reseller), run_jobs)
        data = document["data"]

        assert list(data) == [*CLIENT_SECTIONS, "reseller"]
        assert data["account"]["referral_code"] == reseller.referral_code
        section = data["reseller"]
        assert list(section) == ["summary", "sales", "commissions", "statements", "payouts"]
        assert section["sales"][0]["product"] == "Galaxy A55"
        assert section["sales"][0]["total"] == "100.00"
        assert {entry["amount"] for entry in section["commissions"]} >= {"10.00"}
        statement = section["statements"][0]
        assert statement["status"] == "paid"
        assert statement["lines"]
        assert section["payouts"][0]["note"] == "M-Pesa"
        assert section["payouts"][0]["statement_id"] == statement["id"]
        assert section["summary"]["paid_total"] == section["payouts"][0]["amount"]
        # the customer's identity and the purchase cost stay out
        assert "Jean Mukendi" not in raw
        assert "unit_cost" not in raw
        assert "profit" not in raw
        assert "Activité de revendeur" in html

    def test_assigned_threads_hold_only_the_resellers_own_messages(
        self, as_user, reseller, shopper, run_jobs
    ):
        thread = Conversation.objects.create(
            kind="support", client=shopper, assigned_reseller=reseller, subject="Livraison"
        )
        Message.objects.create(conversation=thread, sender=shopper, body="Message du client")
        Message.objects.create(conversation=thread, sender=reseller, body="J'arrive à 15 h")

        document, raw, _ = download(as_user(reseller), run_jobs)

        (exported,) = document["data"]["messages"]["threads"]
        assert exported["own_messages_only"] is True
        assert [message["body"] for message in exported["messages"]] == ["J'arrive à 15 h"]
        assert "Message du client" not in raw

    def test_clients_get_no_reseller_section(self, as_user, shopper, run_jobs):
        document, _, _ = download(as_user(shopper), run_jobs)

        assert "reseller" not in document["data"]


class TestAccessRules:
    def test_only_the_owner_downloads(self, as_user, api, shopper, run_jobs):
        job_id = export(as_user(shopper), run_jobs)["id"]

        other = as_user(UserFactory.create())
        assert other.get(f"{EXPORT}{job_id}/download/").status_code == 404
        assert other.get(EXPORT).json()["job"] is None
        api.force_authenticate(None)
        assert api.get(f"{EXPORT}{job_id}/download/").status_code == 401
        assert api.post(EXPORT).status_code == 401

    def test_back_office_job_routes_do_not_serve_it(self, as_user, reseller, run_jobs):
        api = as_user(reseller)
        job_id = export(api, run_jobs)["id"]

        assert api.get("/api/v1/jobs/").json()["meta"]["count"] == 0
        assert api.get(f"/api/v1/jobs/{job_id}/").status_code == 404
        assert api.get(f"/api/v1/jobs/{job_id}/download/").status_code == 404

    def test_pending_exports_cannot_be_downloaded(self, as_user, shopper):
        api = as_user(shopper)
        job_id = api.post(EXPORT).json()["id"]

        response = api.get(f"{EXPORT}{job_id}/download/")

        assert response.status_code == 409
        assert response.json()["code"] == "job_not_ready"


class TestThrottle:
    def test_once_per_hour(self, as_user, shopper, run_jobs):
        api = as_user(shopper)
        export(api, run_jobs)

        response = api.post(EXPORT)

        assert response.status_code == 429
        assert response.json()["code"] == "personal_data_export_too_soon"
        available_at = response.json()["meta"]["available_at"]
        assert api.get(EXPORT).json()["available_at"] == available_at
        assert Job.objects.count() == 1
        Job.objects.update(created_at=timezone.now() - timedelta(minutes=61))
        assert api.post(EXPORT).status_code == 202
        assert api.get(EXPORT).json()["job"]["status"] == "pending"

    def test_per_user(self, as_user, shopper, run_jobs):
        export(as_user(shopper), run_jobs)

        assert as_user(UserFactory.create()).post(EXPORT).status_code == 202

    @pytest.mark.usefixtures("exploding_export")
    def test_a_failed_export_can_be_retried(self, as_user, shopper, run_jobs):
        api = as_user(shopper)
        with run_jobs():
            api.post(EXPORT)
        assert api.get(EXPORT).json()["job"]["status"] == "failed"

        assert api.post(EXPORT).status_code == 202


class TestExpiry:
    def test_the_link_expires(self, as_user, shopper, run_jobs):
        api = as_user(shopper)
        job_id = export(api, run_jobs)["id"]
        Job.objects.update(finished_at=timezone.now() - timedelta(hours=49))

        response = api.get(f"{EXPORT}{job_id}/download/")

        assert response.status_code == 404
        assert response.json()["code"] == "job_expired"
        status = api.get(EXPORT).json()["job"]
        assert status["expired"] is True
        assert status["downloadable"] is False

    def test_expired_files_are_purged(self, as_user, shopper, reseller, run_jobs):
        export(as_user(shopper), run_jobs)
        with run_jobs():
            as_user(reseller).post("/api/v1/bo/sales/export/", {"format": "csv"}, format="json")
        Job.objects.filter(kind="personal_data").update(
            finished_at=timezone.now() - timedelta(hours=49)
        )

        assert container.resolve(DocumentJobFacade).purge() == 1
        assert list(Job.objects.values_list("kind", flat=True)) == ["sales_export"]

    def test_the_purge_runs_every_hour(self):
        assert settings.CELERY_BEAT_SCHEDULE["purge-document-jobs"]["schedule"] == 60 * 60


class TestAudit:
    def test_requests_and_downloads_are_recorded(self, as_user, shopper, run_jobs):
        api = as_user(shopper)
        job_id = export(api, run_jobs)["id"]
        with run_jobs():
            api.get(f"{EXPORT}{job_id}/download/")

        records = {
            record.event_type.rsplit(".", 1)[-1]: record
            for record in EventRecord.objects.filter(event_type__contains="PersonalData")
        }
        assert set(records) == {"PersonalDataRequested", "PersonalDataDownloaded"}
        for record in records.values():
            assert record.actor_id == shopper.pk
            assert record.payload == {"job_id": job_id, "owner_id": shopper.pk}

    def test_refused_downloads_are_not_recorded(self, as_user, shopper, run_jobs):
        job_id = export(as_user(shopper), run_jobs)["id"]
        with run_jobs():
            as_user(ResellerFactory.create()).get(f"{EXPORT}{job_id}/download/")

        assert not EventRecord.objects.filter(event_type__endswith="PersonalDataDownloaded")
