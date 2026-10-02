from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response

from core.api.problems import PROBLEM_CONTENT_TYPE, Problem
from core.domain.errors import DomainError, Forbidden, NotFound, ValidationFailed

NON_FIELD_ERRORS = "non_field_errors"


def problem_exception_handler(exc: Exception, context: Mapping[str, Any]) -> Response | None:
    problem = to_problem(exc)
    if problem is None:
        return None
    response = Response(problem.as_dict(), status=problem.status, content_type=PROBLEM_CONTENT_TYPE)
    if auth_header := getattr(exc, "auth_header", None):
        response["WWW-Authenticate"] = auth_header
    if (wait := getattr(exc, "wait", None)) is not None:
        response["Retry-After"] = str(int(wait))
    return response


def to_problem(exc: Exception) -> Problem | None:
    match exc:
        case DomainError():
            return Problem.from_domain(exc)
        case exceptions.ValidationError():
            return _validation_problem(exc.detail)
        case DjangoValidationError():
            detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
            return _validation_problem(detail)
        case exceptions.APIException():
            return Problem(
                status=exc.status_code, code=_api_code(exc), detail=_plain_text(exc.detail)
            )
        case Http404():
            return Problem.from_domain(NotFound())
        case DjangoPermissionDenied():
            return Problem.from_domain(Forbidden())
        case _:
            return None


def not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return _json_problem(Problem.from_domain(NotFound()))


def server_error(request: HttpRequest) -> JsonResponse:
    return _json_problem(
        Problem(
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="server_error",
            detail="Une erreur interne est survenue.",
        )
    )


def _json_problem(problem: Problem) -> JsonResponse:
    return JsonResponse(
        problem.as_dict(),
        status=problem.status,
        content_type=PROBLEM_CONTENT_TYPE,
        json_dumps_params={"ensure_ascii": False},
    )


def _validation_problem(detail: Any) -> Problem:
    plain = _plain(detail)
    errors = plain if isinstance(plain, dict) else {NON_FIELD_ERRORS: _as_list(plain)}
    return Problem(
        status=HTTPStatus.BAD_REQUEST,
        code=ValidationFailed.default_code,
        detail=ValidationFailed.default_detail,
        errors=errors,
    )


def _api_code(exc: exceptions.APIException) -> str:
    code = getattr(exc.detail, "code", None)
    return code if isinstance(code, str) else str(exc.default_code)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return str(value)


def _plain_text(value: Any) -> str:
    plain = _plain(value)
    if isinstance(plain, list):
        return " ".join(str(item) for item in plain)
    if isinstance(plain, dict):
        return " ".join(str(item) for item in plain.values())
    return str(plain)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]
