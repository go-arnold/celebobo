import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, override_settings

from apps.accounts.tests.factories import AdminFactory
from apps.catalog.adapters.database import DatabaseSearch
from apps.catalog.admin import CategoryAdmin, ProductAdmin
from apps.catalog.domain.events import CategoryChanged, ProductRemoved
from apps.catalog.models import Category, Product
from apps.catalog.providers import register
from apps.catalog.services.contracts import SearchEngine
from apps.catalog.services.search import ResilientSearch
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from core.container import Container

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_request():
    request = RequestFactory().post("/django-admin/")
    request.user = AdminFactory.create()
    return request


class TestAdminPublishesEvents:
    def test_category_save_and_delete(self, admin_request, published_events):
        category = CategoryFactory.create()
        model_admin = CategoryAdmin(Category, AdminSite())

        form = model_admin.get_form(admin_request, category)(instance=category)
        model_admin.save_model(admin_request, category, form=form, change=True)
        model_admin.delete_model(admin_request, category)

        events = published_events.of_type(CategoryChanged)
        assert [event.category_id for event in events] == [category.pk, category.pk]
        assert Category.deleted_objects.filter(pk=category.pk).exists()

    def test_product_deletions_are_soft_and_published(self, admin_request, published_events):
        first, second, third = ProductFactory.create_batch(3)
        model_admin = ProductAdmin(Product, AdminSite())

        model_admin.delete_model(admin_request, first)
        model_admin.delete_queryset(
            admin_request, Product.objects.filter(pk__in=[second.pk, third.pk])
        )

        removed = {event.product_id for event in published_events.of_type(ProductRemoved)}
        assert removed == {first.pk, second.pk, third.pk}
        assert Product.deleted_objects.count() == 3


class TestProviders:
    def test_database_engine_by_default(self):
        target = Container()
        register(target)

        assert isinstance(target.resolve(SearchEngine), DatabaseSearch)

    @override_settings(CATALOG={"SEARCH_ENGINE": "meilisearch"})
    def test_meilisearch_is_wrapped_with_a_database_fallback(self):
        target = Container()
        register(target)

        assert isinstance(target.resolve(SearchEngine), ResilientSearch)
