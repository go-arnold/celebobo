from celery import shared_task

from apps.standing.facades import StandingFacade
from core.container import container

REVIEW_TASK = "standing.review_levels"


# daily: on the first day of each quarter, every reseller's level is reviewed
@shared_task(name=REVIEW_TASK)
def review_levels() -> None:
    container.resolve(StandingFacade).review_if_due()
