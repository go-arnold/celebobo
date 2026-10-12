from celery import shared_task

from apps.catalog.facades import DealAdminFacade
from core.container import container

ANNOUNCE_DEALS_TASK = "catalog.announce_deals"


@shared_task(name=ANNOUNCE_DEALS_TASK)
def announce_deals() -> None:
    container.resolve(DealAdminFacade).announce()
