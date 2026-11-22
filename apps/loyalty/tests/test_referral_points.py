"""Referral points: 0.3 % of an invited client's invoices for the reseller (policy, 3.3)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import ResellerFactory, UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.loyalty.facades import PointsFacade
from apps.loyalty.models import LoyaltySettings, PointsEntry
from apps.loyalty.tests.test_points import balance, credit, place, status_changed
from apps.orders.domain.enums import OrderStatus
from apps.orders.models import Order
from core.container import container

pytestmark = pytest.mark.django_db


@pytest.fixture
def programme():
    LoyaltySettings.objects.update_or_create(pk=1, defaults={"points_enabled": True})


@pytest.fixture
def reseller():
    return ResellerFactory.create()


@pytest.fixture
def invited(reseller):
    return UserFactory.create(invited_by=reseller, invited_at=timezone.now() - timedelta(days=30))


@pytest.fixture
def headset():
    # the reseller policy's example: a $149 headset earns the reseller 0.45 point
    return ProductFactory.create(price=Decimal("149.00"), stock=20)


def referral_of(reseller):
    return PointsEntry.objects.filter(user=reseller, kind="referral")


def delivered(user, product, **options):
    order = place(user, product, **options)
    Order.objects.filter(pk=order["id"]).update(status="delivered")
    status_changed(order["id"], OrderStatus.DELIVERED)
    return order


class TestEarning:
    def test_the_inviting_reseller_gets_0_3_percent_of_the_items(
        self, programme, reseller, invited, headset
    ):
        order = delivered(invited, headset)

        entry = referral_of(reseller).get()
        # 0.3 % of 149 = 0.447, rounded to the nearest cent as in the policy; delivery excluded
        assert (entry.amount, entry.order_id) == (Decimal("0.45"), order["id"])
        mine = balance(reseller)
        assert (mine["available"], mine["pending"]) == ("0.00", "0.45")
        assert mine["history"][0]["kind"] == "referral"
        # the client still earns their own 1 %
        assert PointsEntry.objects.get(user=invited, kind="earn").amount == Decimal("1.49")

    def test_the_history_does_not_tie_the_points_to_an_order(
        self, programme, reseller, invited, headset
    ):
        order = delivered(invited, headset)
        status_changed(order["id"], OrderStatus.RETURNED)

        history = balance(reseller)["history"]

        # the order number would let the reseller work back each invitee's purchase total
        # (privacy policy, 4): a referral line shows only its kind, date and amount
        assert {(row["kind"], row["order_number"]) for row in history} == {
            ("referral", None),
            ("referral_reversal", None),
        }
        # the client keeps the number on their own points
        assert balance(invited)["history"][0]["order_number"] == order["number"]

    def test_once_the_return_period_is_over_the_points_are_spendable(
        self, programme, reseller, invited, headset
    ):
        delivered(invited, headset)
        referral_of(reseller).update(available_at=timezone.now() - timedelta(minutes=1))

        assert balance(reseller)["available"] == "0.45"

    def test_delivering_twice_pays_once(self, programme, reseller, invited, headset):
        order = delivered(invited, headset)

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert referral_of(reseller).count() == 1

    def test_nothing_for_a_client_nobody_invited(self, programme, reseller, headset):
        delivered(UserFactory.create(), headset)

        assert not referral_of(reseller).exists()

    def test_nothing_while_the_programme_is_off(self, reseller, invited, headset):
        delivered(invited, headset)

        assert not referral_of(reseller).exists()


class TestNonRealMoney:
    def test_nothing_when_the_order_used_points(self, programme, reseller, invited, headset):
        credit(invited, "5.00")

        delivered(invited, headset, points="5")

        assert not referral_of(reseller).exists()

    def test_nothing_when_the_order_used_a_coupon(self, programme, reseller, invited, headset):
        order = place(invited, headset)
        Order.objects.filter(pk=order["id"]).update(
            status="delivered", discount=Decimal("10.00"), total=Decimal(order["total"]) - 10
        )

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert not referral_of(reseller).exists()


class TestWindow:
    def test_nothing_twelve_months_after_the_invitation(
        self, programme, reseller, invited, headset
    ):
        invited.invited_at = timezone.now() - timedelta(days=370)
        invited.save(update_fields=["invited_at"])

        delivered(invited, headset)

        assert not referral_of(reseller).exists()

    def test_nothing_once_the_reseller_left(self, programme, reseller, invited, headset):
        reseller.is_active = False
        reseller.save(update_fields=["is_active"])

        delivered(invited, headset)

        assert not referral_of(reseller).exists()


class TestReturns:
    def test_a_returned_order_takes_the_referral_back(self, programme, reseller, invited, headset):
        order = delivered(invited, headset)

        status_changed(order["id"], OrderStatus.RETURNED)

        assert referral_of(reseller).get().remaining == 0
        reversal = PointsEntry.objects.get(user=reseller, kind="referral_reversal")
        assert reversal.amount == Decimal("-0.45")
        # the client's own reversal is unaffected
        assert PointsEntry.objects.get(user=invited, kind="reversal").amount == Decimal("-1.49")

    def test_a_returned_line_takes_back_its_share(self, programme, reseller, invited, headset):
        order = place(invited, headset, key="checkout-0002")
        Order.objects.filter(pk=order["id"]).update(status="delivered")
        status_changed(order["id"], OrderStatus.DELIVERED)

        # half of the real money comes back: half of the referral goes
        container.resolve(PointsFacade).line_returned(order["id"], Decimal("74.50"), Decimal(0))

        reversal = PointsEntry.objects.get(user=reseller, kind="referral_reversal")
        assert reversal.amount == Decimal("-0.22")


class TestValidity:
    def test_referral_points_alone_count_from_the_latest_one(self, programme, reseller):
        PointsEntry.objects.create(
            user=reseller,
            kind="referral",
            amount=Decimal("2.00"),
            remaining=Decimal("2.00"),
            available_at=timezone.now() - timedelta(days=1),
        )

        expiry = balance(reseller)["next_expiry"]

        assert expiry is not None
        assert container.resolve(PointsFacade).expire() == 0

    def test_referral_points_do_not_restart_a_buying_resellers_count(
        self, programme, reseller, headset
    ):
        place(reseller, headset, key="checkout-0003")
        long_ago = timezone.now() - timedelta(days=400)
        Order.objects.filter(client=reseller).update(created_at=long_ago)
        PointsEntry.objects.create(
            user=reseller,
            kind="referral",
            amount=Decimal("2.00"),
            remaining=Decimal("2.00"),
            available_at=timezone.now() - timedelta(days=1),
        )

        # the last purchase is over 12 months old: the whole balance expires
        assert container.resolve(PointsFacade).expire() == 1
