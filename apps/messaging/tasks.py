from celery import shared_task

from apps.messaging.facades import ConversationFacade
from core.container import container

CLOSE_EXPIRED_TASK = "messaging.close_expired_threads"


@shared_task(name=CLOSE_EXPIRED_TASK)
def close_expired_threads() -> int:
    return container.resolve(ConversationFacade).close_expired()
