from celery import shared_task

from apps.loyalty.facades import MembershipFacade, PointsFacade
from core.container import container

REMIND_TASK = "loyalty.remind_memberships"
EXPIRE_TASK = "loyalty.expire_points"


@shared_task(name=REMIND_TASK)
def remind_memberships() -> None:
    container.resolve(MembershipFacade).remind()


@shared_task(name=EXPIRE_TASK)
def expire_points() -> None:
    container.resolve(PointsFacade).expire()
