from __future__ import annotations

from typing import Any

from celery import Task
from celery.signals import before_task_publish, task_postrun, task_prerun

from core.observability import context

REQUEST_ID_HEADER = "request_id"


def install_context_propagation() -> None:
    before_task_publish.connect(_inject_request_id, weak=False)
    task_prerun.connect(_bind_task_context, weak=False)
    task_postrun.connect(_clear_task_context, weak=False)


def _inject_request_id(headers: dict[str, Any] | None = None, **_: Any) -> None:
    request_id = context.current_request_id()
    if headers is not None and request_id:
        headers.setdefault(REQUEST_ID_HEADER, request_id)


def _bind_task_context(
    task_id: str | None = None, task: Task[Any, Any] | None = None, **_: Any
) -> None:
    request = getattr(task, "request", None)
    request_id = getattr(request, REQUEST_ID_HEADER, None) or (
        (getattr(request, "headers", None) or {}).get(REQUEST_ID_HEADER)
    )
    context.reset(request_id=request_id, task=getattr(task, "name", None), task_id=task_id)


def _clear_task_context(**_: Any) -> None:
    context.reset()
