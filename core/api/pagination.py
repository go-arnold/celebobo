from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


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
