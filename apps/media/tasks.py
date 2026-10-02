from celery import shared_task

from apps.media.facades import MediaMaintenanceFacade
from core.container import container

SWEEP_TASK = "media.sweep_orphans"


@shared_task(name=SWEEP_TASK)
def sweep_orphans() -> int:
    return container.resolve(MediaMaintenanceFacade).sweep_orphans().deleted
