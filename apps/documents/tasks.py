from celery import shared_task

from apps.documents.facades import DocumentJobFacade
from core.container import container

PURGE_TASK = "documents.purge_jobs"


@shared_task(name=PURGE_TASK)
def purge_jobs() -> int:
    return container.resolve(DocumentJobFacade).purge()
