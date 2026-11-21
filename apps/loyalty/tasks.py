from celery import shared_task

from apps.loyalty.facades import PointsFacade
from core.container import container

EXPIRE_TASK = "loyalty.expire_points"


@shared_task(name=EXPIRE_TASK)
def expire_points() -> None:
    container.resolve(PointsFacade).expire()
