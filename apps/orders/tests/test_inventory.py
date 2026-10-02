from decimal import Decimal

import pytest

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.errors import OutOfStock, ProductUnavailable, VariantRequired
from apps.catalog.domain.events import ProductChanged
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.facades import InventoryFacade
from apps.catalog.models import Product, StockMovement
from apps.catalog.tests.factories import ProductFactory, VariantFactory
from core.container import container

pytestmark = pytest.mark.django_db

SOURCE = StockSource(kind="order", id=99, actor_id=None)


@pytest.fixture
def inventory() -> InventoryFacade:
    return container.resolve(InventoryFacade)


class TestPricing:
    def test_prices_simple_and_variant_lines(self, inventory):
        simple = ProductFactory.create(price=Decimal(100), sale_price=Decimal(80))
        variant = VariantFactory.create(price=Decimal(150), label="Bleu / 256 Go")

        lines = inventory.price(
            [
                StockLine(product_id=simple.pk, quantity=2),
                StockLine(product_id=variant.product_id, variant_id=variant.pk, quantity=1),
            ]
        )

        assert [(line.unit_price, line.total) for line in lines] == [
            (Decimal(80), Decimal(160)),
            (Decimal(150), Decimal(150)),
        ]
        assert lines[1].variant_label == "Bleu / 256 Go"
        assert lines[1].sku == variant.sku

    def test_variant_products_need_a_variant(self, inventory):
        variant = VariantFactory.create()

        with pytest.raises(VariantRequired):
            inventory.price([StockLine(product_id=variant.product_id, quantity=1)])

    def test_hidden_products_are_unavailable(self, inventory):
        product = ProductFactory.create(is_active=False)

        with pytest.raises(ProductUnavailable):
            inventory.price([StockLine(product_id=product.pk, quantity=1)])


class TestReservation:
    def test_reserve_and_release(self, published_events, inventory):
        product = ProductFactory.create(stock=5)

        inventory.reserve([StockLine(product_id=product.pk, quantity=2)] * 2, SOURCE)
        product.refresh_from_db()
        assert product.stock == 1

        inventory.release(
            [StockLine(product_id=product.pk, quantity=4)],
            SOURCE,
            reason=StockReason.ORDER,
            note="Annulation",
        )
        product.refresh_from_db()
        assert product.stock == 5
        movements = list(
            StockMovement.objects.order_by("pk").values_list("delta", "balance_after", "reason")
        )
        assert movements == [(-4, 1, "order"), (4, 5, "order")]
        assert len(published_events.of_type(ProductChanged)) == 2

    def test_variants_decrement_both_levels(self, inventory):
        variant = VariantFactory.create(stock=3)
        Product.objects.filter(pk=variant.product_id).update(stock=3)

        inventory.reserve(
            [StockLine(product_id=variant.product_id, variant_id=variant.pk, quantity=2)], SOURCE
        )

        variant.refresh_from_db()
        assert variant.stock == 1
        assert Product.objects.get(pk=variant.product_id).stock == 1

    def test_insufficient_stock(self, inventory):
        product = ProductFactory.create(stock=1)

        with pytest.raises(OutOfStock) as error:
            inventory.reserve([StockLine(product_id=product.pk, quantity=2)], SOURCE)

        assert error.value.meta["available"] == 1
        assert error.value.detail == "Stock insuffisant (1 disponible)."
        product.refresh_from_db()
        assert product.stock == 1
