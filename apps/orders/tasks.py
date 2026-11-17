from celery import shared_task

from apps.orders.facades import OrderExpiryFacade
from core.container import container

EXPIRE_TASK = "orders.expire_stale"


@shared_task(name=EXPIRE_TASK)
def expire_stale_orders() -> int:
    return container.resolve(OrderExpiryFacade).expire_stale()
