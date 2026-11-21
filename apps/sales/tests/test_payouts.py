from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.tests.factories import ResellerFactory
from apps.messaging.models import Notification
from apps.orders.models import Order, OrderStatusEvent
from apps.sales.domain.events import PayoutRecorded, PayoutStatementPrepared
from apps.sales.domain.payouts import VALIDATION_DAYS, PayoutCalendar
from apps.sales.facades import CommissionFacade
from apps.sales.models import CommissionEntry, DeliveryCredit, Payout, PayoutStatement, Sale
from apps.sales.repositories import StatementRepository
from apps.sales.services.statements import StatementService
from core.container import container

pytestmark = pytest.mark.django_db

COMMISSIONS = "/api/v1/bo/commissions/"
STATEMENTS = "/api/v1/bo/payout-statements/"
PAYOUTS = "/api/v1/bo/payouts/"
BO_ORDERS = "/api/v1/bo/orders/"
SALES = "/api/v1/bo/sales/"


def days_ago(days: int) -> datetime:
    return timezone.now() - timedelta(days=days)


def payout_date() -> date:
    return PayoutCalendar().next(timezone.localdate())


def prepare(day: date | None = None) -> int:
    return container.resolve(CommissionFacade).prepare_statements(day or payout_date())


def summary(api, reseller) -> dict[str, Any]:
    body: dict[str, Any] = api.get(f"{COMMISSIONS}summary/", {"reseller_id": reseller.pk}).json()
    return body


def earned(sale_id: int) -> Decimal:
    return CommissionEntry.objects.get(sale_id=sale_id, kind="earned").amount


# a ledger line already validated, for the threshold rules (independent of how much a sale earns)
def ledger(reseller, amount: str, *, validated_days_ago: int = 3) -> CommissionEntry:
    return CommissionEntry.objects.create(
        reseller=reseller,
        kind="earned",
        rule="paid",
        base_amount=Decimal(amount) * 10,
        amount=Decimal(amount),
        available_at=days_ago(validated_days_ago),
    )


def pay(api, statement_id: int, key: str = "payout-000001", **extra):
    return api.post(
        PAYOUTS,
        {"statement_id": statement_id, "note": "M-Pesa", **extra},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def refund(api, sale_id: int, key: str, **payload):
    return api.post(
        f"{SALES}{sale_id}/refund/",
        {"kind": "refund", **payload},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def deliver(api, order: Order, reseller) -> None:
    assert api.post(f"{BO_ORDERS}{order.pk}/assign/", {"reseller_id": reseller.pk}).status_code
    response = api.post(
        f"{BO_ORDERS}{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    assert response.status_code == 200, response.json()


class TestCalendar:
    @pytest.mark.parametrize(
        ("day", "following", "latest"),
        [
            (date(2026, 12, 1), date(2026, 12, 1), date(2026, 12, 1)),
            (date(2026, 12, 2), date(2026, 12, 16), date(2026, 12, 1)),
            (date(2026, 12, 16), date(2026, 12, 16), date(2026, 12, 16)),
            (date(2026, 12, 31), date(2027, 1, 1), date(2026, 12, 16)),
        ],
    )
    def test_payouts_fall_on_the_1st_and_the_16th(self, day, following, latest):
        assert PayoutCalendar().next(day) == following
        assert PayoutCalendar().latest(day) == latest

    def test_statements_are_prepared_on_payout_days_only(self):
        def at(day: int) -> StatementService:
            moment = timezone.make_aware(datetime(2026, 12, day, 9, 0))
            return StatementService(StatementRepository(), clock=lambda: moment)

        assert at(1).payout_date() == date(2026, 12, 1)
        assert at(16).payout_date() == date(2026, 12, 16)
        assert at(5).payout_date() is None
        assert at(5).next_payout_date() == date(2026, 12, 16)

    def test_the_task_runs_every_hour(self):
        assert settings.CELERY_BEAT_SCHEDULE["prepare-payout-statements"] == {
            "task": "sales.prepare_payouts",
            "schedule": 60 * 60,
        }


class TestValidation:
    def test_a_manual_sale_stays_pending_seven_days_after_the_sale(
        self, as_user, reseller, record_sale
    ):
        sale = record_sale(reseller)
        entry = CommissionEntry.objects.get(sale_id=sale["id"])
        amount = entry.amount

        body = summary(as_user(reseller), reseller)

        sold_at = Sale.objects.get(pk=sale["id"]).sold_at
        assert entry.available_at == sold_at + timedelta(days=VALIDATION_DAYS)
        assert Decimal(body["pending"]) == amount
        assert body["validated"] == "0.00"
        assert body["due"] == "0.00"

    def test_validated_once_the_trial_period_is_over(self, as_user, reseller, record_sale):
        sale = record_sale(reseller, sold_at=days_ago(8).isoformat())
        amount = earned(sale["id"])

        body = summary(as_user(reseller), reseller)
        entries = as_user(reseller).get(COMMISSIONS).json()["results"]

        assert body["pending"] == "0.00"
        assert Decimal(body["validated"]) == amount
        assert Decimal(body["due"]) == amount
        assert entries[0]["status"] == "validated"

    @pytest.fixture
    def order(self, shopper, phone, place_order) -> Order:
        return Order.objects.get(number=place_order(shopper, phone, quantity=2)["number"])

    def test_an_order_sale_counts_from_the_delivery(self, as_user, manager, reseller, order):
        api = as_user(manager)
        deliver(api, order, reseller)
        converted = api.post(
            f"{BO_ORDERS}{order.pk}/convert-to-sales/",
            {"sold_at": days_ago(20).isoformat()},
            format="json",
            HTTP_IDEMPOTENCY_KEY="convert-000001",
        )
        assert converted.status_code == 201, converted.json()

        entry = CommissionEntry.objects.get()
        delivered_at = OrderStatusEvent.objects.get(order=order, to_status="delivered").created_at
        # sold 20 days ago on paper, but delivered just now: still pending
        assert entry.available_at == delivered_at + timedelta(days=VALIDATION_DAYS)
        assert summary(api, reseller)["validated"] == "0.00"

    def test_a_refund_before_validation_cancels_the_pending_commission(
        self, as_user, manager, reseller, record_sale
    ):
        sale = record_sale(reseller)

        assert refund(as_user(manager), sale["id"], "refund-000001").status_code == 200

        body = summary(as_user(manager), reseller)
        entries = as_user(reseller).get(COMMISSIONS).json()["results"]
        assert body["pending"] == "0.00"
        assert body["validated"] == "0.00"
        assert {entry["status"] for entry in entries} == {"cancelled"}
        assert prepare() == 0

    def test_a_refund_after_validation_takes_it_back(self, as_user, manager, reseller, record_sale):
        sale = record_sale(reseller, sold_at=days_ago(10).isoformat())

        refund(as_user(manager), sale["id"], "refund-000002")

        body = summary(as_user(manager), reseller)
        assert body["validated"] == "0.00"
        assert body["due"] == "0.00"

    def test_a_partial_refund_stays_proportional(self, as_user, manager, reseller, record_sale):
        sale = record_sale(reseller, sold_at=days_ago(10).isoformat())
        amount = earned(sale["id"])

        refund(as_user(manager), sale["id"], "refund-000003", amount="50.00")

        body = summary(as_user(manager), reseller)
        # a quarter of the $200 sale was refunded
        assert Decimal(body["validated"]) == amount - (amount / 4).quantize(Decimal("0.01"))
        assert entries_status(as_user(reseller)) == {"validated"}


def entries_status(api) -> set[str]:
    return {entry["status"] for entry in api.get(COMMISSIONS).json()["results"]}


class TestStatements:
    def test_prepared_for_a_payable_balance(self, reseller, published_events):
        line = ledger(reseller, "6.00")
        # validated only after the payout date: waits for the next one
        ledger(reseller, "9.00", validated_days_ago=-20)

        assert prepare() == 1

        statement = PayoutStatement.objects.get()
        assert statement.payout_date == payout_date()
        assert statement.status == "prepared"
        assert statement.total == Decimal("6.00")
        line.refresh_from_db()
        assert line.statement_id == statement.pk
        assert CommissionEntry.objects.filter(statement__isnull=True).count() == 1
        assert any(isinstance(e, PayoutStatementPrepared) for e in published_events.events)

    def test_below_five_dollars_it_rolls_over(self, reseller):
        ledger(reseller, "4.99")
        first = payout_date()

        assert prepare(first) == 0
        assert not PayoutStatement.objects.exists()

        ledger(reseller, "1.00")
        following = PayoutCalendar().next(first + timedelta(days=1))
        assert prepare(following) == 1
        assert PayoutStatement.objects.get().total == Decimal("5.99")

    def test_once_per_reseller_and_date(self, reseller):
        ledger(reseller, "10.00")

        assert prepare() == 1
        ledger(reseller, "10.00")
        assert prepare() == 0
        assert PayoutStatement.objects.count() == 1

    def test_an_unpaid_statement_is_replaced_on_the_next_date(self, reseller):
        ledger(reseller, "10.00")
        first = payout_date()
        prepare(first)
        ledger(reseller, "5.00")

        prepare(PayoutCalendar().next(first + timedelta(days=1)))

        old, new = PayoutStatement.objects.order_by("payout_date")
        assert old.status == "cancelled"
        assert new.status == "prepared"
        assert new.total == Decimal("15.00")

    def test_a_refund_updates_the_prepared_statement(self, as_user, manager, reseller, record_sale):
        sale = record_sale(reseller, sold_at=days_ago(10).isoformat())
        amount = earned(sale["id"])
        prepare()

        refund(as_user(manager), sale["id"], "refund-000004", amount="50.00")

        statement = PayoutStatement.objects.get()
        assert statement.total == amount - (amount / 4).quantize(Decimal("0.01"))
        assert CommissionEntry.objects.filter(statement=statement).count() == 2

        refund(as_user(manager), sale["id"], "refund-000005")

        statement.refresh_from_db()
        assert statement.status == "cancelled"
        assert not CommissionEntry.objects.filter(statement__isnull=False).exists()

    def test_deleting_a_sale_takes_it_off_the_prepared_statement(
        self, as_user, admin, reseller, record_sale
    ):
        kept = record_sale(reseller, sold_at=days_ago(10).isoformat())
        deleted = record_sale(reseller, sold_at=days_ago(10).isoformat())
        prepare()

        response = as_user(admin).delete(f"/api/v1/bo/sales/{deleted['id']}/")

        assert response.status_code == 204, response.content
        statement = PayoutStatement.objects.get()
        assert statement.total == earned(kept["id"])
        assert CommissionEntry.objects.filter(statement=statement).count() == 3

    def test_a_refund_after_payment_is_deducted_next_time(
        self, as_user, admin, manager, reseller, record_sale
    ):
        sale = record_sale(reseller, sold_at=days_ago(10).isoformat())
        amount = earned(sale["id"])
        prepare()
        assert pay(as_user(admin), PayoutStatement.objects.get().pk).status_code == 201
        assert entries_status(as_user(reseller)) == {"paid"}

        refund(as_user(manager), sale["id"], "refund-000006")

        body = summary(as_user(manager), reseller)
        assert Decimal(body["due"]) == -amount
        reversal = CommissionEntry.objects.get(kind="reversed")
        assert reversal.statement_id is None
        assert entries_status(as_user(reseller)) == {"cancelled"}

    def test_reseller_sees_lines_of_own_statements_only(self, as_user, manager, reseller):
        ledger(reseller, "7.00")
        other = ResellerFactory.create()
        ledger(other, "8.00")
        prepare()
        mine = PayoutStatement.objects.get(reseller=reseller)
        theirs = PayoutStatement.objects.get(reseller=other)

        listed = as_user(reseller).get(STATEMENTS, {"reseller_id": other.pk}).json()
        detail = as_user(reseller).get(f"{STATEMENTS}{mine.pk}/").json()

        assert [row["id"] for row in listed["results"]] == [mine.pk]
        assert detail["total"] == "7.00"
        assert detail["lines"][0]["kind"] == "commission"
        assert detail["lines"][0]["amount"] == "7.00"
        assert as_user(reseller).get(f"{STATEMENTS}{theirs.pk}/").status_code == 404
        staff = as_user(manager).get(STATEMENTS, {"status": "prepared"}).json()
        assert staff["meta"]["count"] == 2


class TestDeliveryFees:
    @pytest.fixture
    def order(self, shopper, phone, place_order) -> Order:
        return Order.objects.get(number=place_order(shopper, phone)["number"])

    def test_the_delivering_reseller_gets_the_fee_back(self, as_user, manager, reseller, order):
        assert order.shipping_fee > 0
        deliver(as_user(manager), order, reseller)

        credit = DeliveryCredit.objects.get()
        body = summary(as_user(manager), reseller)
        assert credit.reseller_id == reseller.pk
        assert credit.amount == order.shipping_fee
        assert credit.order_number == order.number
        assert Decimal(body["delivery_fees"]) == order.shipping_fee
        assert Decimal(body["due"]) == order.shipping_fee

    def test_nothing_for_a_pickup(self, as_user, manager, reseller, order):
        Order.objects.filter(pk=order.pk).update(delivery_method="pickup")

        deliver(as_user(manager), order, reseller)

        assert not DeliveryCredit.objects.exists()

    def test_nothing_for_a_free_delivery(self, as_user, manager, reseller, order):
        Order.objects.filter(pk=order.pk).update(
            shipping_fee=Decimal(0), total=order.total - order.shipping_fee
        )

        deliver(as_user(manager), order, reseller)

        assert not DeliveryCredit.objects.exists()

    def test_kept_on_a_return_taken_back_on_a_cancellation(self, as_user, manager, reseller, order):
        api = as_user(manager)
        deliver(api, order, reseller)

        returned = api.post(
            f"{BO_ORDERS}{order.pk}/transition/", {"to": "returned", "reason": "Défaut"}
        )
        assert returned.status_code == 200, returned.json()
        assert DeliveryCredit.objects.count() == 1

        container.resolve(CommissionFacade).order_cancelled(order.pk)
        container.resolve(CommissionFacade).order_cancelled(order.pk)

        reversal = DeliveryCredit.objects.get(kind="reversal")
        assert reversal.amount == -order.shipping_fee
        assert summary(api, reseller)["delivery_fees"] == "0.00"

    def test_its_own_line_on_the_statement(self, as_user, manager, reseller, order):
        deliver(as_user(manager), order, reseller)
        ledger(reseller, "6.00")
        tomorrow = timezone.localdate() + timedelta(days=1)

        prepare(PayoutCalendar().next(tomorrow))

        statement = PayoutStatement.objects.get()
        detail = as_user(reseller).get(f"{STATEMENTS}{statement.pk}/").json()
        assert statement.delivery_fees == order.shipping_fee
        assert statement.total == Decimal("6.00") + order.shipping_fee
        fee = next(line for line in detail["lines"] if line["kind"] == "delivery_fee")
        assert fee["order_number"] == order.number
        assert fee["title"] == f"Frais de livraison — commande {order.number}"


class TestPayouts:
    @pytest.fixture
    def statement(self, reseller) -> PayoutStatement:
        ledger(reseller, "20.00")
        prepare()
        return PayoutStatement.objects.get()

    def test_admins_pay_a_prepared_statement(
        self, as_user, admin, reseller, statement, published_events
    ):
        response = pay(as_user(admin), statement.pk)

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["amount"] == "20.00"
        assert body["statement_id"] == statement.pk
        assert body["paid_by"]["id"] == admin.pk
        statement.refresh_from_db()
        assert statement.status == "paid"
        assert statement.payout_id == body["id"]
        totals = summary(as_user(admin), reseller)
        assert totals["paid_total"] == "20.00"
        assert totals["due"] == "0.00"
        assert any(isinstance(e, PayoutRecorded) for e in published_events.events)

    def test_a_statement_is_paid_once(self, as_user, admin, statement):
        first = pay(as_user(admin), statement.pk, key="payout-twice-1")
        retry = pay(as_user(admin), statement.pk, key="payout-twice-1")
        again = pay(as_user(admin), statement.pk, key="payout-twice-2")

        assert retry.json()["id"] == first.json()["id"]
        assert again.status_code == 409
        assert again.json()["code"] == "statement_not_payable"
        assert Payout.objects.count() == 1

    def test_never_more_than_what_is_due(self, as_user, admin, reseller, statement):
        # a later deduction (a commission cancelled after it was paid) lowers what is due
        ledger(reseller, "-15.00")

        response = pay(as_user(admin), statement.pk)

        assert response.status_code == 400
        assert response.json()["code"] == "payout_exceeds_due"
        assert response.json()["meta"]["due"] == "5.00"

    def test_unknown_statement(self, as_user, admin):
        assert pay(as_user(admin), 999_999).status_code == 404

    def test_managers_and_resellers_cannot_pay(self, as_user, manager, reseller, statement):
        assert pay(as_user(manager), statement.pk).status_code == 403
        assert pay(as_user(reseller), statement.pk).status_code == 403

    def test_listing_is_scoped(self, as_user, admin, reseller, statement):
        pay(as_user(admin), statement.pk)
        other = ResellerFactory.create()

        assert as_user(reseller).get(PAYOUTS).json()["meta"]["count"] == 1
        assert (
            as_user(other).get(PAYOUTS, {"reseller_id": reseller.pk}).json()["meta"]["count"] == 0
        )
        assert as_user(admin).get(PAYOUTS).json()["results"][0]["payout_date"] == (
            statement.payout_date.isoformat()
        )


@pytest.mark.django_db(transaction=True)
def test_resellers_are_notified_of_statements_and_payments(as_user, admin, reseller):
    ledger(reseller, "12.50")

    prepare()
    statement = PayoutStatement.objects.get()
    pay(as_user(admin), statement.pk)

    day = f"{statement.payout_date:%d/%m/%Y}"
    prepared = Notification.objects.get(kind="payout_statement")
    paid = Notification.objects.get(kind="payout_paid")
    assert prepared.recipient_id == reseller.pk
    assert prepared.title == f"Relevé de paiement du {day}"
    assert "12.50 $" in prepared.body
    assert prepared.link == f"/admin/commissions?releve={statement.pk}"
    assert paid.recipient_id == reseller.pk
    assert paid.body == f"Celebobo vous a versé 12.50 $ pour votre relevé du {day}."
