from celery import shared_task

from apps.audit.facades import AuditFacade
from core.container import container

PURGE_TASK = "audit.purge"
RETENTION_TASK = "audit.apply_retention"


@shared_task(name=PURGE_TASK)
def purge_audit_trail() -> dict[str, int]:
    return container.resolve(AuditFacade).purge()


# one beat entry per rule (see CELERY_BEAT_SCHEDULE), so a failing rule never blocks the others
@shared_task(name=RETENTION_TASK)
def apply_retention(rule: str) -> int:
    return container.resolve(AuditFacade).apply_retention(rule).affected
