from typing import Any

from celery import shared_task

from core.events.execution import run_background_handler


@shared_task(
    name="core.events.dispatch",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def dispatch_event(handler_path: str, event_name: str, payload: dict[str, Any]) -> None:
    run_background_handler(handler_path, event_name, payload)
