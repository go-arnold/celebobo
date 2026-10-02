from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from types import MappingProxyType
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param

from core.domain.errors import ValidationFailed


class PaginationStyle(StrEnum):
    PAGE = "page"
    CURSOR = "cursor"


class MetaPaginationMixin:
    _extra_meta: Mapping[str, Any] = MappingProxyType({})

    def set_meta(self, **meta: Any) -> None:
        self._extra_meta = meta

    def _envelope(
        self, data: Any, next_link: str | None, previous_link: str | None, meta: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "results": data,
            "next": next_link,
            "previous": previous_link,
            "meta": {**meta, **self._extra_meta},
        }

    @staticmethod
    def _envelope_schema(results: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        link = {"type": "string", "nullable": True, "format": "uri"}
        return {
            "type": "object",
            "required": ["results", "next", "previous", "meta"],
            "properties": {
                "results": results,
                "next": link,
                "previous": link,
                "meta": {"type": "object", "properties": meta, "additionalProperties": True},
            },
        }


class PagePagination(MetaPaginationMixin, PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: Any) -> Response:
        page = self.page
        if page is None:
            raise ImproperlyConfigured("paginate_queryset() must run before the response")
        meta = {
            "count": page.paginator.count,
            "page": page.number,
            "page_size": page.paginator.per_page,
            "total_pages": page.paginator.num_pages,
        }
        return Response(self._envelope(data, self.get_next_link(), self.get_previous_link(), meta))

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        integer = {"type": "integer"}
        return self._envelope_schema(
            schema,
            {"count": integer, "page": integer, "page_size": integer, "total_pages": integer},
        )


class CursorMetaPagination(MetaPaginationMixin, CursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"

    def get_paginated_response(self, data: Any) -> Response:
        meta = {"page_size": self.page_size}
        return Response(self._envelope(data, self.get_next_link(), self.get_previous_link(), meta))

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return self._envelope_schema(schema, {"page_size": {"type": "integer"}})


type PaginationClass = type[PagePagination] | type[CursorMetaPagination]

_BASES: Mapping[PaginationStyle, PaginationClass] = MappingProxyType(
    {PaginationStyle.PAGE: PagePagination, PaginationStyle.CURSOR: CursorMetaPagination}
)


def paginated(
    style: PaginationStyle = PaginationStyle.PAGE,
    *,
    page_size: int | None = None,
    max_page_size: int | None = None,
    ordering: str | Sequence[str] | None = None,
) -> PaginationClass:
    if ordering is not None and style is PaginationStyle.PAGE:
        raise ImproperlyConfigured("ordering only applies to cursor pagination")
    base = _BASES[style]
    overrides = {
        name: value
        for name, value in {
            "page_size": page_size,
            "max_page_size": max_page_size,
            "ordering": ordering,
        }.items()
        if value is not None
    }
    if not overrides:
        return base
    return type(base.__name__, (base,), overrides)


@dataclass(frozen=True, slots=True)
class PageRequest:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_request(request: Request, *, default_size: int = 20, max_size: int = 100) -> PageRequest:
    page = _positive_int(request.query_params.get("page"), 1, "page")
    size = _positive_int(request.query_params.get("page_size"), default_size, "page_size")
    return PageRequest(page=page, page_size=min(size, max_size))


def page_response(
    request: Request,
    page: PageRequest,
    *,
    total: int,
    results: Any,
    meta: Mapping[str, Any] | None = None,
) -> Response:
    total_pages = max(1, ceil(total / page.page_size))
    url = request.build_absolute_uri()
    next_link = replace_query_param(url, "page", page.page + 1) if page.page < total_pages else None
    previous_link = _previous_link(url, page.page)
    return Response(
        {
            "results": results,
            "next": next_link,
            "previous": previous_link,
            "meta": {
                "count": total,
                "page": page.page,
                "page_size": page.page_size,
                "total_pages": total_pages,
                **(meta or {}),
            },
        }
    )


def _positive_int(raw: str | None, default: int, field: str) -> int:
    if raw in (None, ""):
        return default
    try:
        value = int(str(raw))
    except ValueError:
        value = 0
    if value < 1:
        raise ValidationFailed(errors={field: ["Entier positif attendu."]})
    return value


def _previous_link(url: str, page: int) -> str | None:
    if page == 1:
        return None
    if page - 1 == 1:
        return remove_query_param(url, "page")
    return replace_query_param(url, "page", page - 1)


class PageMetaOutput(serializers.Serializer[Any]):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()


_PAGES: dict[type[serializers.BaseSerializer[Any]], type[serializers.Serializer[Any]]] = {}


def page_of(
    serializer_class: type[serializers.BaseSerializer[Any]],
) -> type[serializers.Serializer[Any]]:
    if serializer_class not in _PAGES:
        name = serializer_class.__name__.removesuffix("Output")
        page = type(
            f"{name}Page",
            (serializers.Serializer,),
            {
                "results": serializer_class(many=True),
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "meta": PageMetaOutput(),
            },
        )
        _PAGES[serializer_class] = extend_schema_serializer(many=False)(page)
    return _PAGES[serializer_class]
