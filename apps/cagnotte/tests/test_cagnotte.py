"""Cagnotte operations (loyalty policy): on top of the 1 % points, one at a time."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import (
    AdminFactory,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)
from apps.cagnotte.domain.rules import CampaignKind, Scope, Terms, advantage, overlaps
from apps.cagnotte.handlers import settle_reward
from apps.cagnotte.models import Campaign, Reward
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.loyalty.facades import PointsFacade
from apps.loyalty.handlers import settle_points
from apps.loyalty.models import LoyaltySettings, PointsEntry
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from apps.orders.models import Coupon, CouponRedemption, Order
from core.container import container

pytestmark = pytest.mark.django_db

ADDRESS = {
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Ibanda",
    "city": "Bukavu",
    "country": "RD Congo",
}
CAMPAIGNS = "/api/v1/bo/campaigns/"
REWARDS = "/api/v1/bo/cagnotte/rewards/"


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def programme():
    LoyaltySettings.objects.update_or_create(pk=1, defaults={"points_enabled": True})


@pytest.fixture
def admin():
    return AdminFactory.create()


@pytest.fixture
def client_user():
    return UserFactory.create()


def running(**fields) -> Campaign:
    now = timezone.now()
    values = {
        "name": "Fête des mères",
        "kind": CampaignKind.CASHBACK.value,
        "percent": Decimal("3.00"),
        "starts_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=10),
    } | fields
    return Campaign.objects.create(**values)


def body(**fields):
    now = timezone.now()
    return {
        "name": "Rentrée",
        "kind": "cashback",
        "percent": "3.00",
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=15)).isoformat(),
    } | fields


def create(user, key="campaign-000001", **fields):
    return as_api(user).post(CAMPAIGNS, body(**fields), format="json", HTTP_IDEMPOTENCY_KEY=key)


def place(user, products, *, key="checkout-0001", coupon=None):
    payload = {
        "lines": [{"product_id": p.pk, "quantity": 1} for p in products],
        "payment_method": "cash",
        "address": ADDRESS,
    }
    if coupon:
        payload["coupon_code"] = coupon
    response = as_api(user).post(
        "/api/v1/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key
    )
    assert response.status_code == 201, response.json()
    return Order.objects.get(pk=response.json()["id"])


def delivered(order: Order) -> None:
    event = OrderStatusChanged(
        order_id=order.pk,
        client_id=order.client_id,
        reseller_id=None,
        previous_status=OrderStatus.SHIPPING,
        status=OrderStatus.DELIVERED,
    )
    settle_points(event)
    settle_reward(event)


def undone(order: Order) -> None:
    settle_reward(
        OrderStatusChanged(
            order_id=order.pk,
            client_id=order.client_id,
            reseller_id=None,
            previous_status=OrderStatus.DELIVERED,
            status=OrderStatus.RETURNED,
        )
    )


class TestRules:
    def test_minimum_and_cap(self):
        terms = Terms(
            kind=CampaignKind.CASHBACK,
            percent=Decimal("3"),
            min_purchase=Decimal("50"),
            cap=Decimal("5"),
        )
        assert advantage(terms, Decimal("49.99")) == Decimal("0.00")
        assert advantage(terms, Decimal("100")) == Decimal("3.00")
        assert advantage(terms, Decimal("1000")) == Decimal("5")

    def test_one_at_a_time(self):
        day = datetime(2026, 12, 1, tzinfo=timezone.get_current_timezone())
        others = [(day, day + timedelta(days=5))]
        assert overlaps(day + timedelta(days=4), day + timedelta(days=9), others)
        # touching periods are fine
        assert not overlaps(day + timedelta(days=5), day + timedelta(days=9), others)

    def test_scope(self):
        assert Scope(category_ids=frozenset(), product_ids=frozenset()).covers(1, [])
        scope = Scope(category_ids=frozenset({7}), product_ids=frozenset({3}))
        assert scope.covers(3, [])
        assert scope.covers(9, [7])
        assert not scope.covers(9, [8])


class TestCampaignsApi:
    def test_admin_sets_up_an_operation(self, admin, programme):
        category = CategoryFactory.create()
        response = create(admin, category_ids=[category.pk], min_purchase="50.00", cap="20.00")
        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["state"] == "upcoming"
        assert data["kind_label"] == "Cashback"
        assert data["categories"] == [{"id": category.pk, "name": category.name}]
        assert data["payout"] == "points"

    def test_one_operation_at_a_time(self, admin, programme):
        assert create(admin).status_code == 201
        second = create(admin, key="campaign-000002")
        assert second.status_code == 422
        assert second.json()["code"] == "campaign_overlap"

    def test_points_need_the_programme(self, admin):
        response = create(admin, kind="boosted_points")
        assert response.json()["code"] == "points_disabled"
        mobile = create(admin, key="campaign-000002", payout="mobile_money")
        assert mobile.status_code == 201

    @pytest.mark.parametrize(
        "fields",
        [{"percent": "0"}, {"percent": "60"}, {"points_valid_days": 0}, {"cap": "0"}],
    )
    def test_invalid_conditions(self, admin, programme, fields):
        response = create(admin, **fields)
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_campaign"

    def test_conditions_are_fixed_once_started(self, admin, programme):
        campaign = running()
        url = f"{CAMPAIGNS}{campaign.pk}/"
        changed = as_api(admin).put(url, body(), format="json")
        assert changed.json()["code"] == "campaign_started"
        assert as_api(admin).delete(url).json()["code"] == "campaign_started"
        ended = as_api(admin).post(f"{url}end/")
        assert ended.json()["state"] == "ended"
        assert as_api(admin).post(f"{url}end/").json()["code"] == "campaign_ended"

    def test_an_upcoming_operation_can_change_or_go(self, admin, programme):
        campaign_id = create(admin).json()["id"]
        url = f"{CAMPAIGNS}{campaign_id}/"
        changed = as_api(admin).put(url, body(name="Rentrée 2027"), format="json")
        assert changed.json()["name"] == "Rentrée 2027"
        assert as_api(admin).delete(url).status_code == 204
        assert not Campaign.objects.exists()

    def test_only_admins_set_up_operations(self):
        assert create(ManagerFactory.create()).status_code == 403
        assert create(UserFactory.create()).status_code == 403

    def test_the_shop_sees_the_running_operation(self):
        anonymous = APIClient()
        assert anonymous.get("/api/v1/cagnotte/current/").json() == {"campaign": None}
        running(description="3 % sur tout le site")
        current = anonymous.get("/api/v1/cagnotte/current/").json()["campaign"]
        assert current["name"] == "Fête des mères"
        assert current["description"] == "3 % sur tout le site"


class TestDiscount:
    def test_only_the_products_concerned_are_discounted(self, client_user):
        phones = CategoryFactory.create()
        phone = ProductFactory.create(price=Decimal("200.00"), stock=5, category=phones)
        case = ProductFactory.create(price=Decimal("20.00"), stock=5)
        campaign = running(kind="discount", percent=Decimal("10.00"))
        campaign.categories.set([phones])

        quote = (
            as_api(client_user)
            .post(
                "/api/v1/checkout/quote/",
                {"lines": [{"product_id": p.pk, "quantity": 1} for p in (phone, case)]},
                format="json",
            )
            .json()
        )
        assert quote["campaign_name"] == "Fête des mères"
        assert quote["campaign_discount"] == "20.00"
        assert quote["discount"] == "20.00"

        order = place(client_user, [phone, case])
        assert order.campaign_id == campaign.pk
        assert order.campaign_discount == Decimal("20.00")
        assert order.discount == Decimal("20.00")
        assert order.total == Decimal("200.00") + order.shipping_fee
        by_product = {item.product_id: item for item in order.items.all()}
        assert by_product[phone.pk].campaign_discount == Decimal("20.00")
        assert by_product[phone.pk].amount_paid == Decimal("180.00")
        assert by_product[case.pk].amount_paid == Decimal("20.00")

    def test_points_stay_one_percent_of_what_was_paid(self, programme, client_user):
        product = ProductFactory.create(price=Decimal("100.00"), stock=5)
        running(kind="discount", percent=Decimal("10.00"))
        order = place(client_user, [product])
        delivered(order)
        assert PointsEntry.objects.get(order=order, kind="earn").amount == Decimal("0.90")
        # a discount brings no cashback
        assert not Reward.objects.exists()

    def test_cap_and_minimum(self, client_user):
        cheap = ProductFactory.create(price=Decimal("40.00"), stock=5)
        dear = ProductFactory.create(price=Decimal("500.00"), stock=5)
        running(
            kind="discount", percent=Decimal("10.00"), min_purchase=Decimal("50"), cap=Decimal("30")
        )
        assert place(client_user, [cheap]).campaign_discount == Decimal("0.00")
        other = UserFactory.create()
        assert place(other, [dear], key="checkout-0002").campaign_discount == Decimal("30.00")

    def test_a_coupon_applies_to_what_is_left(self, client_user):
        phone = ProductFactory.create(price=Decimal("200.00"), stock=5)
        case = ProductFactory.create(price=Decimal("100.00"), stock=5)
        campaign = running(kind="discount", percent=Decimal("10.00"))
        campaign.products.set([phone])
        Coupon.objects.create(code="DIX", kind="percent", value=Decimal("10.00"))
        order = place(client_user, [phone, case], coupon="DIX")
        # Cagnotte: 20 on the phone; coupon: 10 % of the 280 left
        assert (order.campaign_discount, order.discount) == (Decimal("20.00"), Decimal("48.00"))
        assert CouponRedemption.objects.get(order=order).amount == Decimal("28.00")
        by_product = {item.product_id: item for item in order.items.all()}
        assert by_product[phone.pk].discount == Decimal("38.00")
        assert by_product[case.pk].discount == Decimal("10.00")
        assert sum(item.amount_paid for item in order.items.all()) == Decimal("252.00")


class TestCashbackInPoints:
    def test_points_on_top_of_the_one_percent_with_their_own_validity(self, programme, client_user):
        product = ProductFactory.create(price=Decimal("100.00"), stock=5)
        running(points_valid_days=30)
        order = place(client_user, [product])
        assert order.campaign_discount == Decimal("0.00")
        delivered(order)
        earn = PointsEntry.objects.get(order=order, kind="earn")
        cagnotte = PointsEntry.objects.get(order=order, kind="cagnotte")
        assert (earn.amount, cagnotte.amount) == (Decimal("1.00"), Decimal("3.00"))
        assert cagnotte.available_at == earn.available_at
        assert cagnotte.expires_at == cagnotte.available_at + timedelta(days=30)
        reward = Reward.objects.get(order=order)
        assert (reward.status, reward.kept) == ("credited", Decimal("3.00"))
        mine = as_api(client_user).get("/api/v1/me/cagnotte/").json()
        assert mine[0]["order_number"] == order.number

    def test_a_returned_order_loses_its_cagnotte_points(self, programme, client_user):
        product = ProductFactory.create(price=Decimal("100.00"), stock=5)
        running(kind="boosted_points")
        order = place(client_user, [product])
        delivered(order)
        undone(order)
        entry = PointsEntry.objects.get(order=order, kind="cagnotte")
        assert entry.remaining == Decimal("0.00")
        assert PointsEntry.objects.get(order=order, kind="cagnotte_reversal").amount == Decimal(
            "-3.00"
        )
        assert Reward.objects.get(order=order).kept == Decimal("0.00")

    def test_cagnotte_points_expire_on_their_own_date(self, programme, client_user):
        product = ProductFactory.create(price=Decimal("100.00"), stock=5)
        running()
        order = place(client_user, [product])
        delivered(order)
        PointsEntry.objects.filter(kind="cagnotte").update(
            available_at=timezone.now() - timedelta(days=40),
            expires_at=timezone.now() - timedelta(days=1),
        )
        PointsEntry.objects.filter(kind="earn").update(
            available_at=timezone.now() - timedelta(days=40)
        )
        container.resolve(PointsFacade).expire()
        assert PointsEntry.objects.get(kind="cagnotte").remaining == Decimal("0.00")
        # the 1 % points follow the 12-month rule: still there
        assert PointsEntry.objects.get(kind="earn").remaining == Decimal("1.00")
        mine = as_api(client_user).get("/api/v1/me/points/").json()
        assert mine["available"] == "1.00"

    def test_the_invoice_prints_the_cagnotte_points(self, programme, client_user):
        product = ProductFactory.create(price=Decimal("100.00"), stock=5)
        running()
        order = place(client_user, [product])
        delivered(order)
        statement = container.resolve(PointsFacade).invoice_statement(client_user.pk, order.pk)
        assert statement is not None
        assert statement.cagnotte == Decimal("3.00")


class TestCashbackByMobileMoney:
    @pytest.fixture
    def reward(self, client_user):
        product = ProductFactory.create(price=Decimal("200.00"), stock=5)
        running(payout="mobile_money")
        order = place(client_user, [product])
        delivered(order)
        return Reward.objects.get(order=order)

    def test_sent_by_staff_once_the_trial_is_over(
        self, reward, client_user, django_capture_on_commit_callbacks
    ):
        assert (reward.status, reward.amount) == ("to_pay", Decimal("6.00"))
        assert not PointsEntry.objects.filter(kind="cagnotte").exists()
        manager = as_api(ManagerFactory.create())
        assert manager.get(REWARDS, {"due": True}).json()["meta"]["count"] == 0
        early = manager.post(f"{REWARDS}{reward.pk}/pay/", {"reference": "MP-1"})
        assert early.json()["code"] == "reward_not_due"

        Reward.objects.filter(pk=reward.pk).update(available_at=timezone.now())
        due = manager.get(REWARDS, {"due": True}).json()
        assert due["results"][0]["phone"] == ADDRESS["phone"]
        with django_capture_on_commit_callbacks(execute=True):
            paid = manager.post(f"{REWARDS}{reward.pk}/pay/", {"reference": "MP-7731"})
        assert paid.json()["status"] == "paid"
        assert client_user.notifications.filter(kind="cashback_paid").exists()
        again = manager.post(f"{REWARDS}{reward.pk}/pay/", {"reference": "MP-7731"})
        assert again.json()["code"] == "reward_not_due"

    def test_returned_before_payment_cancels_after_payment_is_owed_back(self, reward):
        order = Order.objects.get(pk=reward.order_id)
        Reward.objects.filter(pk=reward.pk).update(
            status="paid", paid_at=timezone.now(), reference="MP-1"
        )
        undone(order)
        reward.refresh_from_db()
        assert (reward.kept, reward.owed_back) == (Decimal("0.00"), Decimal("6.00"))

    def test_returned_before_payment_is_cancelled(self, reward):
        undone(Order.objects.get(pk=reward.order_id))
        reward.refresh_from_db()
        assert (reward.status, reward.kept) == ("cancelled", Decimal("0.00"))

    def test_only_staff_send_cashbacks(self, reward):
        assert as_api(ResellerFactory.create()).get(REWARDS).status_code == 403
        assert as_api(UserFactory.create()).get(REWARDS).status_code == 403


class TestLineReturn:
    def test_returning_units_takes_back_their_share(
        self, programme, client_user, django_capture_on_commit_callbacks
    ):
        product = ProductFactory.create(price=Decimal("100.00"), stock=5)
        running()
        response = as_api(client_user).post(
            "/api/v1/orders/",
            {
                "lines": [{"product_id": product.pk, "quantity": 2}],
                "payment_method": "cash",
                "address": ADDRESS,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="checkout-lines-1",
        )
        order = Order.objects.get(pk=response.json()["id"])
        staff = as_api(ManagerFactory.create())
        staff.post(
            f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": ResellerFactory.create().pk}
        )
        with django_capture_on_commit_callbacks(execute=True):
            staff.post(
                f"/api/v1/bo/orders/{order.pk}/transition/",
                {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
            )
        assert Reward.objects.get(order=order).kept == Decimal("6.00")
        item = order.items.get()
        with django_capture_on_commit_callbacks(execute=True):
            returned = staff.post(
                f"/api/v1/bo/orders/{order.pk}/items/{item.pk}/return/",
                {"quantity": 1},
                format="json",
                HTTP_IDEMPOTENCY_KEY="return-0001",
            )
        assert returned.status_code == 200, returned.json()
        assert Reward.objects.get(order=order).kept == Decimal("3.00")
        assert PointsEntry.objects.get(order=order, kind="cagnotte").remaining == Decimal("3.00")
