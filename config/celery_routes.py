from collections.abc import Sequence
from typing import Any

EVENT_TASK = "core.events.dispatch"
QUEUES = (
    (("apps.assistant.", "assistant."), "ai"),
    (("apps.documents.", "documents."), "exports"),
)


def route_task(name: str, args: Sequence[Any], *_: Any, **__: Any) -> dict[str, str] | None:
    target = str(args[0]) if name == EVENT_TASK and args else name
    for prefixes, queue in QUEUES:
        if target.startswith(prefixes):
            return {"queue": queue}
    return None
