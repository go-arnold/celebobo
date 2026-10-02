import pytest

from apps.analytics.domain.events import SalesFactsRefreshed
from apps.analytics.facades import FactsFacade
from apps.analytics.models import SalesFact
from apps.analytics.tasks import refresh_sales_facts
from core.container import container

pytestmark = pytest.mark.django_db


def test_recording_a_sale_refreshes_the_facts(
    reseller, phone, sell, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        sell(reseller, phone, quantity=3)

    fact = SalesFact.objects.get()
    assert fact.units == 3
    assert str(fact).endswith(f"produit {phone.pk}")


def test_refreshes_are_debounced():
    facts = container.resolve(FactsFacade)

    assert facts.claim_refresh() is True
    assert facts.claim_refresh() is False
    facts.refresh()
    assert facts.claim_refresh() is True


def test_the_beat_task_announces_fresh_numbers(published_events):
    refresh_sales_facts()

    assert published_events.single(SalesFactsRefreshed)
