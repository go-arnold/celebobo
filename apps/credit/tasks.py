from celery import shared_task

from apps.credit.facades import StoreCreditFacade
from core.container import container

EXPIRE_TASK = "credit.expire"


# daily: what is left of a store credit after 6 months is lost
@shared_task(name=EXPIRE_TASK)
def expire_store_credit() -> None:
    container.resolve(StoreCreditFacade).expire()
