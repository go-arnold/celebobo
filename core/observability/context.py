from typing import Any

import structlog


def bind(**values: Any) -> None:
    structlog.contextvars.bind_contextvars(**values)


def reset(**values: Any) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**values)


def current(key: str) -> Any:
    return structlog.contextvars.get_contextvars().get(key)


def current_request_id() -> str | None:
    value = current("request_id")
    return value if isinstance(value, str) else None
