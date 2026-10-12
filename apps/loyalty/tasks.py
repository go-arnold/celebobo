from celery import shared_task

from apps.loyalty.facades import MembershipFacade
from core.container import container

REMIND_TASK = "loyalty.remind_memberships"


@shared_task(name=REMIND_TASK)
def remind_memberships() -> None:
    container.resolve(MembershipFacade).remind()
