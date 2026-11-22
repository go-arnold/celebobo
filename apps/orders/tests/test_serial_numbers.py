"""Serial numbers and IMEIs of the units sold (warranty policy): recorded before the order leaves,
printed on the invoice and the delivery receipt."""

from datetime import date

import pytest

from apps.catalog.models import Product
from apps.orders.domain import serials
from apps.orders.domain.events import SerialNumbersRecorded
from apps.orders.models import Order, OrderItemSerial

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"
IMEI_A, IMEI_B = "352099001761481", "490154203237518"


@pytest.fixture
def tracked(phone) -> Product:
    Product.objects.filter(pk=phone.pk).update(serial_required=True)
    product: Product = Product.objects.get(pk=phone.pk)
    return product


@pytest.fixture
def order(as_user, shopper, tracked, place_order, *, manager, reseller) -> Order:
    order = Order.objects.get(number=place_order(shopper, tracked, quantity=2)["number"])
    as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
    api = as_user(reseller)
    for status in ("confirmed", "paid"):
        assert api.post(f"{BO}{order.pk}/transition/", {"to": status}).status_code == 200
    order.refresh_from_db()
    return order


def item_of(order: Order) -> int:
    return order.items.get().pk


def record(api, order: Order, *values: str):
    return api.put(
        f"{BO}{order.pk}/items/{item_of(order)}/serials/", {"serials": list(values)}, format="json"
    )


class TestRules:
    @pytest.mark.parametrize(
        ("raw", "normalized"),
        [("35 209900 176148 1", "352099001761481"), (" r58n12abc3d ", "R58N12ABC3D")],
    )
    def test_spaces_and_case_do_not_matter(self, raw, normalized):
        assert serials.normalize(raw) == normalized

    def test_an_imei_must_have_the_right_check_digit(self):
        assert serials.problem(IMEI_A) is None
        assert serials.problem("352099001761482") is not None

    @pytest.mark.parametrize("value", ["AB", "C02-XY1.2/3", "R58N12ABC3D", "SN 01"])
    def test_maker_serials(self, value):
        expected_ok = value != "AB"
        assert (serials.problem(serials.normalize(value)) is None) is expected_ok

    def test_warranty_runs_one_month_from_the_delivery(self):
        assert serials.warranty_end(date(2026, 1, 31)) == date(2026, 2, 28)
        assert serials.warranty_end(date(2026, 12, 15)) == date(2027, 1, 15)


class TestRecording:
    def test_the_assigned_reseller_records_each_unit(
        self, as_user, reseller, shopper, order, published_events
    ):
        response = record(as_user(reseller), order, IMEI_A, "49 0154 2032 3751 8")

        assert response.status_code == 200, response.json()
        line = response.json()["items"][0]
        assert (line["serial_required"], line["serials"]) == (True, [IMEI_A, IMEI_B])
        event = published_events.single(SerialNumbersRecorded)
        assert (event.count, event.actor_id) == (2, reseller.pk)
        # the client sees them on their order too
        mine = as_user(shopper).get(f"{MINE}{order.number}/").json()
        assert mine["items"][0]["serials"] == [IMEI_A, IMEI_B]

    def test_the_list_replaces_what_was_recorded(self, as_user, reseller, order):
        api = as_user(reseller)
        record(api, order, IMEI_A, IMEI_B)

        response = record(api, order, IMEI_B)

        assert response.json()["items"][0]["serials"] == [IMEI_B]

    def test_a_wrong_imei_is_refused(self, as_user, reseller, order):
        response = record(as_user(reseller), order, "352099001761482")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_serial_number"
        assert not OrderItemSerial.objects.exists()

    def test_never_more_numbers_than_units(self, as_user, reseller, order):
        response = record(as_user(reseller), order, IMEI_A, IMEI_B, "R58N12ABC3D")

        assert response.status_code == 400
        assert response.json()["code"] == "too_many_serial_numbers"

    def test_one_unit_is_not_on_two_running_orders(
        self, as_user, shopper, tracked, place_order, *, reseller, manager, order
    ):
        record(as_user(reseller), order, IMEI_A)
        other = Order.objects.get(number=place_order(shopper, tracked)["number"])
        as_user(manager).post(f"{BO}{other.pk}/assign/", {"reseller_id": reseller.pk})

        response = record(as_user(reseller), other, IMEI_A)

        assert response.status_code == 409
        assert response.json()["meta"] == {"serial": IMEI_A, "order_number": order.number}

    def test_a_cancelled_order_releases_its_units(
        self, as_user, shopper, tracked, place_order, *, reseller, manager, order
    ):
        record(as_user(reseller), order, IMEI_A)
        as_user(manager).post(f"{BO}{order.pk}/transition/", {"to": "cancelled"})
        other = Order.objects.get(number=place_order(shopper, tracked)["number"])
        as_user(manager).post(f"{BO}{other.pk}/assign/", {"reseller_id": reseller.pk})

        assert record(as_user(reseller), other, IMEI_A).status_code == 200

    def test_another_reseller_cannot(self, as_user, order):
        from apps.accounts.tests.factories import ResellerFactory

        response = record(as_user(ResellerFactory.create()), order, IMEI_A)

        assert response.status_code in (403, 404)


class TestBeforeLeaving:
    def test_the_order_cannot_leave_without_every_number(self, as_user, reseller, order):
        api = as_user(reseller)
        record(api, order, IMEI_A)

        response = api.post(f"{BO}{order.pk}/transition/", {"to": "shipping"})

        assert response.status_code == 422, response.json()
        body = response.json()
        assert body["code"] == "serial_numbers_missing"
        assert body["meta"]["lines"] == [
            {"item_id": item_of(order), "name": "Galaxy A55", "missing": 1}
        ]
        order.refresh_from_db()
        assert order.status == "paid"

    def test_once_complete_it_leaves(self, as_user, reseller, order):
        api = as_user(reseller)
        record(api, order, IMEI_A, IMEI_B)

        assert api.post(f"{BO}{order.pk}/transition/", {"to": "shipping"}).status_code == 200

    def test_staff_cannot_skip_to_delivered_either(self, as_user, manager, order):
        response = as_user(manager).post(
            f"{BO}{order.pk}/transition/",
            {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
        )

        assert response.json()["code"] == "serial_numbers_missing"

    def test_products_without_serials_are_not_concerned(
        self, as_user, shopper, phone, place_order, *, reseller, manager
    ):
        order = Order.objects.get(number=place_order(shopper, phone)["number"])
        as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
        api = as_user(reseller)
        for status in ("confirmed", "paid", "shipping"):
            assert api.post(f"{BO}{order.pk}/transition/", {"to": status}).status_code == 200

    def test_after_delivery_only_staff_correct_them(self, as_user, reseller, manager, order):
        record(as_user(reseller), order, IMEI_A, IMEI_B)
        as_user(manager).post(
            f"{BO}{order.pk}/transition/",
            {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
        )

        # `as_user` authenticates the same client: switch back to the reseller
        refused = record(as_user(reseller), order, IMEI_B)
        corrected = record(as_user(manager), order, IMEI_B, "R58N12ABC3D")

        assert refused.json()["code"] == "serial_numbers_not_editable"
        assert corrected.json()["items"][0]["serials"] == [IMEI_B, "R58N12ABC3D"]
