from celery import shared_task

from apps.loyalty.facades import CashbackFacade
from core.container import container

EXPIRE_TASK = "loyalty.expire_cashback"


@shared_task(name=EXPIRE_TASK)
def expire_cashback() -> None:
    container.resolve(CashbackFacade).expire()
