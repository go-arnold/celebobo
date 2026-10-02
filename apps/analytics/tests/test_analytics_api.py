from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db

ANALYTICS = "/api/v1/bo/analytics/"


@pytest.mark.usefixtures("activity")
class TestBreakdowns:
    def test_categories_with_margin_and_share(self, as_user, manager, phones):
        rows = as_user(manager).get(f"{ANALYTICS}categories/").json()

        smartphones = rows[0]
        assert smartphones["category_id"] == phones.pk
        assert smartphones["name"] == "Smartphones"
        assert smartphones["revenue"] == "320.00"
        assert smartphones["profit"] == "80.00"
        assert smartphones["margin_rate"] == "25.0"
        assert smartphones["share"] == 97.0
        assert rows[1]["margin_rate"] == "60.0"

    def test_category_filter(self, as_user, manager, phones):
        response = as_user(manager).get(f"{ANALYTICS}categories/", {"category_id": phones.pk})

        assert [row["category_id"] for row in response.json()] == [phones.pk]

    def test_seller_ranking(self, as_user, manager, reseller):
        rows = as_user(manager).get(f"{ANALYTICS}sellers/").json()

        assert [(row["seller_id"], row["revenue"]) for row in rows] == [
            (reseller.pk, "210.00"),
            (manager.pk, "120.00"),
        ]
        assert rows[0]["name"] == "Patrick Kabasele"
        assert rows[0]["share"] == 63.6

    def test_peak_hours(self, as_user, manager):
        cells = as_user(manager).get(f"{ANALYTICS}peak-hours/").json()

        assert sum(cell["sales_count"] for cell in cells) == 3
        assert all(1 <= cell["weekday"] <= 7 and 0 <= cell["hour"] <= 23 for cell in cells)


def test_slow_movers(as_user, manager, sell, refresh, phone):
    long_ago = timezone.now() - timedelta(days=100)
    dusty = ProductFactory.create(name="Chargeur", stock=7)
    forgotten = ProductFactory.create(name="Écouteurs", stock=3)
    ProductFactory.create(name="Nouveauté", stock=4)
    Product.objects.filter(pk__in=[dusty.pk, forgotten.pk, phone.pk]).update(created_at=long_ago)
    sell(manager, forgotten, days_ago=60)
    sell(manager, phone, days_ago=2)
    refresh()

    rows = as_user(manager).get(f"{ANALYTICS}slow-movers/", {"period": "30d"}).json()

    assert [row["name"] for row in rows] == ["Chargeur", "Écouteurs"]
    assert rows[0]["last_sold_at"] is None
    assert rows[1]["last_sold_at"] is not None
    assert rows[1]["stock"] == 2


def test_resellers_have_no_analytics(as_user, reseller):
    assert as_user(reseller).get(f"{ANALYTICS}categories/").status_code == 403
