from celery import shared_task

from apps.cash.facades import CashFacade
from core.container import container

REMIND_TASK = "cash.remind_overdue"


# hourly: collected money past its 24 hours is reminded to the reseller, once per order
@shared_task(name=REMIND_TASK)
def remind_overdue_cash() -> None:
    container.resolve(CashFacade).remind_overdue()
