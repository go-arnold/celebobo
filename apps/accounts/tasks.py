from typing import Any

from celery import shared_task

from apps.accounts.adapters.mail import build_message


@shared_task(
    name="accounts.deliver_email",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=6,
    acks_late=True,
)
def deliver_email(payload: dict[str, Any]) -> None:
    build_message(payload).send(fail_silently=False)
