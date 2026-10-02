from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.domain.events import CategoryChanged, ProductChanged, ProductRemoved
from apps.catalog.tests.factories import CategoryFactory, FeatureFactory, ProductFactory
from core.container import container
from core.events.contracts import EventPublisher

pytestmark = pytest.mark.django_db


def publish(event, capture) -> None:
    with capture(execute=True):
        container.resolve(EventPublisher).publish(event)


class TestIndexing:
    def test_product_changes_are_indexed(self, search_index, django_capture_on_commit_callbacks):
        product = ProductFactory.create(name="Casque Sony", sale_price=None)
        FeatureFactory.create(product=product, name="Bluetooth 5.3")

        publish(ProductChanged(product_id=product.pk), django_capture_on_commit_callbacks)

        document = search_index.documents[product.pk]
        assert document["name"] == "Casque Sony"
        assert document["features"] == ["Bluetooth 5.3"]
        assert document["on_sale"] is False
        assert document["current_price"] == 100.0

    def test_hidden_products_leave_the_index(
        self, search_index, django_capture_on_commit_callbacks
    ):
        product = ProductFactory.create(is_active=False)

        publish(ProductChanged(product_id=product.pk), django_capture_on_commit_callbacks)

        assert search_index.removed == [product.pk]

    def test_removed_products(self, search_index, django_capture_on_commit_callbacks):
        publish(ProductRemoved(product_id=42), django_capture_on_commit_callbacks)

        assert search_index.removed == [42]

    def test_category_changes_reindex_their_products(
        self, search_index, django_capture_on_commit_callbacks
    ):
        category = CategoryFactory.create()
        products = ProductFactory.create_batch(2, category=category)

        publish(CategoryChanged(category_id=category.pk), django_capture_on_commit_callbacks)

        assert set(search_index.documents) == {product.pk for product in products}

    def test_reindex_command(self, search_index):
        products = ProductFactory.create_batch(3)
        products[0].delete()
        output = StringIO()

        call_command("catalog_reindex", stdout=output)

        assert search_index.configured == 1
        assert len(search_index.documents) == 2
        assert len(search_index.removed) == 1
        assert "3 produits" in output.getvalue()
