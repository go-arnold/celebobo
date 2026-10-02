from apps.analytics.facades import FactsFacade
from apps.analytics.tasks import refresh_sales_facts
from apps.sales.domain.events import SaleDeleted, SaleRecorded, SaleRefunded, SaleUpdated
from core.container import container
from core.events.bus import event_bus


@event_bus.on(SaleRecorded, SaleUpdated, SaleRefunded, SaleDeleted)
def schedule_facts_refresh(_event: SaleRecorded | SaleUpdated | SaleRefunded | SaleDeleted) -> None:
    facts = container.resolve(FactsFacade)
    if facts.claim_refresh():
        refresh_sales_facts.apply_async(countdown=facts.debounce_seconds)
