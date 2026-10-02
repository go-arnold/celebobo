from typing import Any

import structlog
from structlog.typing import Processor


def shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]


def configure_structlog(*, cache_loggers: bool = True) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors(),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=cache_loggers,
    )


def logging_config(*, json_logs: bool, level: str = "INFO") -> dict[str, Any]:
    renderers: list[Processor] = (
        [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
        if json_logs
        else [structlog.dev.ConsoleRenderer()]
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    *renderers,
                ],
                "foreign_pre_chain": shared_processors(),
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "structured"},
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "django.db.backends": {"level": "WARNING"},
            "django.server": {"level": "WARNING"},
            "django.request": {"level": "ERROR"},
        },
    }
