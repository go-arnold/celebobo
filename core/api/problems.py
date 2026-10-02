from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from types import MappingProxyType
from typing import Any

from core.conf import core_settings
from core.domain.errors import (
    BusinessRuleViolation,
    Conflict,
    DomainError,
    Forbidden,
    NotFound,
    ServiceUnavailable,
    Unauthenticated,
    ValidationFailed,
)
from core.observability.context import current_request_id

PROBLEM_CONTENT_TYPE = "application/problem+json"

_STATUS_BY_ERROR: Mapping[type[DomainError], int] = MappingProxyType(
    {
        ValidationFailed: HTTPStatus.BAD_REQUEST,
        Unauthenticated: HTTPStatus.UNAUTHORIZED,
        Forbidden: HTTPStatus.FORBIDDEN,
        NotFound: HTTPStatus.NOT_FOUND,
        Conflict: HTTPStatus.CONFLICT,
        BusinessRuleViolation: HTTPStatus.UNPROCESSABLE_ENTITY,
        ServiceUnavailable: HTTPStatus.SERVICE_UNAVAILABLE,
        DomainError: HTTPStatus.BAD_REQUEST,
    }
)


def status_for(error: DomainError) -> int:
    return next(_STATUS_BY_ERROR[cls] for cls in type(error).__mro__ if cls in _STATUS_BY_ERROR)


@dataclass(frozen=True, slots=True)
class Problem:
    status: int
    code: str
    detail: str
    errors: Mapping[str, Any] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_domain(cls, error: DomainError) -> "Problem":
        return cls(
            status=status_for(error),
            code=error.code,
            detail=error.detail,
            errors={key: list(messages) for key, messages in error.errors.items()},
            meta=dict(error.meta),
        )

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"{core_settings().problem_base_uri.rstrip('/')}/{self.code}",
            "title": HTTPStatus(self.status).phrase,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
        }
        if self.errors:
            body["errors"] = dict(self.errors)
        if self.meta:
            body["meta"] = dict(self.meta)
        if request_id := current_request_id():
            body["request_id"] = request_id
        return body
