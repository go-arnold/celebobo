from celery import shared_task

from apps.analytics.facades import FactsFacade
from core.container import container

REFRESH_TASK = "analytics.refresh_sales_facts"


@shared_task(name=REFRESH_TASK)
def refresh_sales_facts() -> None:
    container.resolve(FactsFacade).refresh()
