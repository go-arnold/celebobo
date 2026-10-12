from celery import shared_task

from apps.loyalty.facades import CashbackFacade, MembershipFacade
from core.container import container

REMIND_TASK = "loyalty.remind_memberships"
EXPIRE_TASK = "loyalty.expire_cashback"


@shared_task(name=REMIND_TASK)
def remind_memberships() -> None:
    container.resolve(MembershipFacade).remind()


@shared_task(name=EXPIRE_TASK)
def expire_cashback() -> None:
    container.resolve(CashbackFacade).expire()
