import asyncio
from typing import cast

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from structlog.testing import capture_logs

from core.domain.errors import NotFound
from core.observability import context
from core.observability.decorators import logged_facade, use_case
from core.observability.middleware import AsyncHandler, SyncHandler, request_context_middleware


def sync_chain(view) -> SyncHandler:
    return cast(SyncHandler, request_context_middleware(view))


def async_chain(view) -> AsyncHandler:
    return cast(AsyncHandler, request_context_middleware(view))


@logged_facade
class CatalogFacade:
    def find(self, product_id: int) -> str:
        if product_id < 0:
            raise NotFound
        if product_id == 0:
            raise RuntimeError("database down")
        return f"product-{product_id}"

    async def find_async(self, product_id: int) -> str:
        return f"product-{product_id}"

    async def stream(self, count: int):
        for index in range(count):
            yield index

    def _helper(self) -> str:
        return "internal"


def events_named(logs, name):
    return [log for log in logs if log["event"] == name]


class TestUseCase:
    def test_success_logs_and_times(self, recorded_metrics):
        with capture_logs() as logs:
            assert CatalogFacade().find(1) == "product-1"

        (log,) = events_named(logs, "use_case.completed")
        assert log["use_case"] == "CatalogFacade.find"
        assert log["duration_ms"] >= 0
        (metric,) = recorded_metrics.named("use_case.duration")
        assert metric.tags == {"use_case": "CatalogFacade.find"}

    def test_domain_error_is_a_rejection(self, recorded_metrics):
        with capture_logs() as logs, pytest.raises(NotFound):
            CatalogFacade().find(-1)

        (log,) = events_named(logs, "use_case.rejected")
        assert log["code"] == "not_found"
        assert recorded_metrics.named("use_case.rejected")[0].tags["code"] == "not_found"

    def test_unexpected_error_is_a_failure(self, recorded_metrics):
        with capture_logs() as logs, pytest.raises(RuntimeError):
            CatalogFacade().find(0)

        assert events_named(logs, "use_case.failed")
        assert recorded_metrics.named("use_case.failed")

    def test_async_methods(self, recorded_metrics):
        with capture_logs() as logs:
            assert asyncio.run(CatalogFacade().find_async(2)) == "product-2"

        assert events_named(logs, "use_case.completed")[0]["use_case"] == "CatalogFacade.find_async"

    def test_async_generators_are_timed_until_exhausted(self, recorded_metrics):
        async def consume():
            return [item async for item in CatalogFacade().stream(3)]

        with capture_logs() as logs:
            assert asyncio.run(consume()) == [0, 1, 2]

        assert events_named(logs, "use_case.completed")

    def test_private_methods_are_not_wrapped(self):
        with capture_logs() as logs:
            CatalogFacade()._helper()

        assert logs == []

    def test_wrapping_twice_is_a_no_op(self):
        wrapped = use_case(CatalogFacade.find)

        assert wrapped is CatalogFacade.find


class TestRequestContextMiddleware:
    def test_generates_request_id_and_binds_context(self, rf: RequestFactory):
        seen = {}

        def view(request):
            seen["request_id"] = context.current_request_id()
            return HttpResponse()

        response = sync_chain(view)(rf.get("/api/v1/products/"))

        assert response["X-Request-ID"] == seen["request_id"]
        assert len(str(seen["request_id"])) == 32

    def test_reports_server_time(self, rf: RequestFactory):
        response = sync_chain(lambda _: HttpResponse())(rf.get("/api/v1/products/"))

        assert response["Server-Timing"].startswith("app;dur=")

    def test_reuses_valid_incoming_request_id(self, rf: RequestFactory):
        middleware = sync_chain(lambda _: HttpResponse())

        response = middleware(rf.get("/", HTTP_X_REQUEST_ID="abc-123-def-456"))

        assert response["X-Request-ID"] == "abc-123-def-456"

    def test_replaces_malformed_request_id(self, rf: RequestFactory):
        middleware = sync_chain(lambda _: HttpResponse())

        response = middleware(rf.get("/", HTTP_X_REQUEST_ID="<script>"))

        assert response["X-Request-ID"] != "<script>"

    def test_logs_requests_except_quiet_paths(self, rf: RequestFactory):
        middleware = sync_chain(lambda _: HttpResponse(status=201))

        with capture_logs() as logs:
            middleware(rf.post("/api/v1/orders/"))
            middleware(rf.get("/health/live/"))

        (log,) = events_named(logs, "http.request")
        assert log["status"] == 201

    def test_async_chain(self, rf: RequestFactory):
        async def view(request):
            return HttpResponse(status=204)

        response = asyncio.run(async_chain(view)(rf.get("/")))

        assert response.status_code == 204
        assert response["X-Request-ID"]
