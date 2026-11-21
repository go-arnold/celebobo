from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.accounts.tests.factories import (
    AdminFactory,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)
from apps.catalog.domain.enums import ProductOrigin
from apps.catalog.domain.errors import InvalidOrigin
from apps.catalog.domain.management_rules import validate_origin
from apps.catalog.models import Product
from apps.catalog.permissions import PRODUCTS_ORIGIN
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from core.authz.catalog import permission_catalog
from core.domain.actor import Role

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/bo/products/"
ORIGIN_FIELDS = {"origin", "partner_gain"}


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def phones():
    return CategoryFactory.create(name="Smartphones", slug="smartphones")


@pytest.fixture
def staff_api() -> APIClient:
    return as_api(ManagerFactory.create())


def payload(category, **overrides):
    return {
        "name": "Écouteurs Oraimo",
        "description": "Des écouteurs sans fil fournis par un partenaire.",
        "category_id": category.pk,
        "price": "30.00",
        "stock": 3,
        **overrides,
    }


def partner(**overrides) -> Product:
    return ProductFactory.create(
        origin=ProductOrigin.PARTNER.value, partner_gain=Decimal("4.00"), **overrides
    )


class TestRules:
    @pytest.mark.parametrize(
        ("origin", "gain"),
        [(ProductOrigin.CELEBOBO, None), (ProductOrigin.PARTNER, Decimal("0.01"))],
    )
    def test_valid_combinations(self, origin, gain):
        validate_origin(origin, gain)

    @pytest.mark.parametrize(
        ("origin", "gain"),
        [
            (ProductOrigin.PARTNER, None),
            (ProductOrigin.PARTNER, Decimal(0)),
            (ProductOrigin.CELEBOBO, Decimal("2.00")),
        ],
    )
    def test_invalid_combinations(self, origin, gain):
        with pytest.raises(InvalidOrigin):
            validate_origin(origin, gain)

    def test_the_database_refuses_inconsistent_rows(self, phones):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProductFactory.create(category=phones, origin=ProductOrigin.PARTNER.value)

    def test_only_managers_and_above_hold_the_permission(self):
        assert PRODUCTS_ORIGIN in permission_catalog.permissions_for(Role.MANAGER)
        assert PRODUCTS_ORIGIN in permission_catalog.permissions_for(Role.ADMIN)
        assert PRODUCTS_ORIGIN not in permission_catalog.permissions_for(Role.RESELLER)
        assert PRODUCTS_ORIGIN not in permission_catalog.permissions_for(Role.CLIENT)


class TestManagers:
    def test_products_default_to_celebobo(self, staff_api, phones):
        body = staff_api.post(PRODUCTS, payload(phones), format="json").json()

        assert body["origin"] == "celebobo"
        assert body["partner_gain"] is None

    def test_create_a_partner_product(self, staff_api, phones):
        response = staff_api.post(
            PRODUCTS, payload(phones, origin="partner", partner_gain="4.50"), format="json"
        )

        assert response.status_code == 201, response.json()
        assert response.json()["origin"] == "partner"
        assert response.json()["partner_gain"] == "4.50"
        product = Product.objects.get(pk=response.json()["id"])
        assert (product.origin, product.partner_gain) == ("partner", Decimal("4.50"))

    @pytest.mark.parametrize(
        "overrides",
        [
            {"origin": "partner"},
            {"origin": "partner", "partner_gain": "0.00"},
            {"origin": "partner", "partner_gain": None},
            {"partner_gain": "3.00"},
            {"origin": "elsewhere"},
        ],
    )
    def test_validation(self, staff_api, phones, overrides):
        response = staff_api.post(PRODUCTS, payload(phones, **overrides), format="json")

        assert response.status_code == 400
        assert not Product.objects.exists()

    def test_switching_back_to_celebobo_drops_the_gain(self, staff_api, phones):
        product = partner(category=phones)

        body = staff_api.patch(
            f"{PRODUCTS}{product.pk}/", {"origin": "celebobo"}, format="json"
        ).json()

        assert (body["origin"], body["partner_gain"]) == ("celebobo", None)

    def test_editing_the_gain_alone(self, staff_api, phones):
        product = partner(category=phones)

        body = staff_api.patch(
            f"{PRODUCTS}{product.pk}/", {"partner_gain": "6.25"}, format="json"
        ).json()

        assert body["partner_gain"] == "6.25"

    def test_a_celebobo_product_has_no_gain(self, staff_api, phones):
        product = ProductFactory.create(category=phones)

        response = staff_api.patch(
            f"{PRODUCTS}{product.pk}/", {"partner_gain": "2.00"}, format="json"
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_product_origin"

    def test_becoming_partner_needs_the_gain(self, staff_api, phones):
        product = ProductFactory.create(category=phones)

        response = staff_api.patch(f"{PRODUCTS}{product.pk}/", {"origin": "partner"}, format="json")

        assert response.status_code == 400

    def test_list_detail_and_duplicate_carry_the_origin(self, phones):
        product = partner(category=phones)
        api = as_api(AdminFactory.create())

        (row,) = api.get(PRODUCTS).json()["results"]
        copy = api.post(f"{PRODUCTS}{product.pk}/duplicate/").json()

        assert (row["origin"], row["partner_gain"]) == ("partner", "4.00")
        assert api.get(f"{PRODUCTS}{product.pk}/").json()["origin"] == "partner"
        assert (copy["origin"], copy["partner_gain"]) == ("partner", "4.00")


class TestHidden:
    def test_resellers_never_see_the_origin(self, phones):
        product = partner(category=phones)
        api = as_api(ResellerFactory.create())

        (row,) = api.get(PRODUCTS).json()["results"]
        detail = api.get(f"{PRODUCTS}{product.pk}/").json()

        assert not ORIGIN_FIELDS & set(row)
        assert not ORIGIN_FIELDS & set(detail)

    def test_the_shop_never_shows_the_origin(self, phones):
        product = partner(category=phones)
        api = as_api(UserFactory.create())

        detail = api.get(f"/api/v1/products/{product.slug}/")
        listing = api.get("/api/v1/products/")

        assert detail.status_code == 200
        assert "partner_gain" not in listing.content.decode()
        assert "origin" not in detail.json()
