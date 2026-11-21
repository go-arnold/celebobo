from celery import shared_task

from apps.sales.facades import CommissionFacade
from core.container import container

PREPARE_PAYOUTS_TASK = "sales.prepare_payouts"


# runs every hour; only the 1st and the 16th prepare anything, once per reseller and date
@shared_task(name=PREPARE_PAYOUTS_TASK)
def prepare_payouts() -> None:
    container.resolve(CommissionFacade).prepare_statements()
