from celery import shared_task

from apps.audit.facades import AuditFacade
from core.container import container

PURGE_TASK = "audit.purge"


@shared_task(name=PURGE_TASK)
def purge_audit_trail() -> dict[str, int]:
    return container.resolve(AuditFacade).purge()
