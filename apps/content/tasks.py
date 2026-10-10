from typing import Any

from celery import shared_task

from apps.content.conf import storefront_settings
from apps.content.domain.errors import RevalidationFailed
from apps.content.facades import StorefrontFacade
from core.container import container

REVALIDATE_TASK = "content.revalidate_storefront"


@shared_task(name=REVALIDATE_TASK, bind=True)
def revalidate_storefront(task: Any, tags: list[str] | None = None) -> None:
    storefront = container.resolve(StorefrontFacade)
    due = tags if tags is not None else storefront.due_tags()
    try:
        storefront.send(due)
    except RevalidationFailed as error:
        raise task.retry(
            args=[due],
            exc=error,
            countdown=2 ** (task.request.retries + 1),
            max_retries=storefront_settings().revalidate_retries,
        ) from error
