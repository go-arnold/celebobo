import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.test import override_settings
from rest_framework import exceptions
from rest_framework.test import APIClient

from core.api.exceptions import problem_exception_handler
from core.api.pagination import CursorMetaPagination, PagePagination, PaginationStyle, paginated
from core.domain.errors import Conflict, InvalidTransition, NotFound, ServiceUnavailable
from core.tests import api_views

pytestmark = pytest.mark.urls("core.tests.api_views")

PROBLEM = "application/problem+json"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _reset_calls():
    api_views.calls.clear()


class TestProblemHandler:
    def handle(self, exc):
        response = problem_exception_handler(exc, {})
        assert response is not None
        return response

    @pytest.mark.parametrize(
        ("error", "status", "code"),
        [
            (NotFound(), 404, "not_found"),
            (Conflict(), 409, "conflict"),
            (InvalidTransition(), 422, "invalid_transition"),
            (ServiceUnavailable(), 503, "service_unavailable"),
            (Http404(), 404, "not_found"),
            (exceptions.NotAuthenticated(), 401, "not_authenticated"),
            (exceptions.MethodNotAllowed("PUT"), 405, "method_not_allowed"),
        ],
    )
    def test_status_and_code(self, error, status, code):
        response = self.handle(error)

        assert response.status_code == status
        assert response.content_type == PROBLEM
        assert response.data["code"] == code
        assert response.data["type"] == f"https://api.test/problems/{code}"
        assert response.data["status"] == status

    def test_drf_validation_errors_keep_field_shape(self):
        response = self.handle(exceptions.ValidationError({"quantity": ["Trop grand."]}))

        assert response.data["errors"] == {"quantity": ["Trop grand."]}
        assert response.data["code"] == "validation_failed"

    def test_list_validation_errors_become_non_field_errors(self):
        response = self.handle(exceptions.ValidationError(["Panier vide."]))

        assert response.data["errors"] == {"non_field_errors": ["Panier vide."]}

    def test_django_validation_errors(self):
        response = self.handle(DjangoValidationError({"price": ["Doit être positif."]}))

        assert response.status_code == 400
        assert response.data["errors"] == {"price": ["Doit être positif."]}

    def test_throttling_sets_retry_after(self):
        response = self.handle(exceptions.Throttled(wait=12.4))

        assert response.status_code == 429
        assert response["Retry-After"] == "13"

    def test_unknown_exceptions_are_left_to_django(self):
        assert problem_exception_handler(RuntimeError(), {}) is None

    def test_meta_and_errors_from_domain(self):
        response = self.handle(Conflict(errors={"order": ["Déjà converti."]}, meta={"id": 3}))

        assert response.data["errors"] == {"order": ["Déjà converti."]}
        assert response.data["meta"] == {"id": 3}


class TestUseCaseViewSet:
    def test_parses_into_dto_and_responds(self, client):
        response = client.post(
            "/api/v1/reservations/",
            {"product_id": 3, "quantity": 2},
            HTTP_IDEMPOTENCY_KEY="key-00000001",
        )

        assert response.status_code == 201
        assert response.json() == {"product_id": 3, "quantity": 2, "requested_by": None}
        assert api_views.calls[0] == api_views.ReserveStock(3, 2, None)

    def test_validation_errors_are_problems(self, client):
        response = client.post(
            "/api/v1/reservations/", {"quantity": 0}, HTTP_IDEMPOTENCY_KEY="key-00000002"
        )

        assert response.status_code == 400
        assert response["Content-Type"] == PROBLEM
        assert set(response.json()["errors"]) == {"product_id", "quantity"}
        assert response.json()["request_id"] == response["X-Request-ID"]

    def test_domain_errors_are_problems(self, client):
        response = client.post(
            "/api/v1/reservations/",
            {"product_id": 3, "quantity": 9},
            HTTP_IDEMPOTENCY_KEY="key-00000003",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "insufficient_stock"
        assert response.json()["meta"] == {"available": 5}


class TestIdempotency:
    url = "/api/v1/reservations/"

    def test_header_is_required(self, client):
        response = client.post(self.url, {"product_id": 1, "quantity": 1})

        assert response.status_code == 400
        assert "Idempotency-Key" in response.json()["errors"]

    def test_malformed_key(self, client):
        response = client.post(
            self.url, {"product_id": 1, "quantity": 1}, HTTP_IDEMPOTENCY_KEY="short"
        )

        assert response.status_code == 400

    def test_replays_successful_response(self, client):
        payload = {"product_id": 1, "quantity": 1}

        first = client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY="replay-key-1")
        second = client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY="replay-key-1")

        assert first.status_code == second.status_code == 201
        assert second.json() == first.json()
        assert second["Idempotent-Replayed"] == "true"
        assert len(api_views.calls) == 1

    def test_reusing_key_with_other_body_is_rejected(self, client):
        client.post(self.url, {"product_id": 1, "quantity": 1}, HTTP_IDEMPOTENCY_KEY="reuse-key-1")

        response = client.post(
            self.url, {"product_id": 1, "quantity": 2}, HTTP_IDEMPOTENCY_KEY="reuse-key-1"
        )

        assert response.status_code == 422
        assert response.json()["code"] == "idempotency_key_reused"

    def test_failed_requests_are_not_stored(self, client):
        client.post(self.url, {"product_id": 1, "quantity": 9}, HTTP_IDEMPOTENCY_KEY="retry-key-1")

        response = client.post(
            self.url, {"product_id": 1, "quantity": 9}, HTTP_IDEMPOTENCY_KEY="retry-key-1"
        )

        assert response.status_code == 422
        assert response.json()["code"] == "insufficient_stock"


@pytest.mark.django_db
class TestSelectorViewSetPagination:
    @pytest.fixture(autouse=True)
    def _groups(self):
        Group.objects.bulk_create(Group(name=name) for name in ("alpha", "beta", "gamma"))

    def test_page_envelope_with_extra_meta(self, client):
        body = client.get("/api/v1/groups/").json()

        assert [item["name"] for item in body["results"]] == ["alpha", "beta"]
        assert body["meta"] == {
            "count": 3,
            "page": 1,
            "page_size": 2,
            "total_pages": 2,
            "total_groups": 3,
        }
        assert body["previous"] is None
        assert "page=2" in body["next"]

    def test_cursor_envelope(self, client):
        first = client.get("/api/v1/group-feed/").json()
        second = client.get(first["next"]).json()

        assert [item["name"] for item in first["results"]] == ["alpha", "beta"]
        assert [item["name"] for item in second["results"]] == ["gamma"]
        assert first["meta"] == {"page_size": 2, "total_groups": 3}

    def test_retrieve(self, client):
        group = Group.objects.get(name="beta")

        assert client.get(f"/api/v1/groups/{group.pk}/").json() == {"id": group.pk, "name": "beta"}

    def test_missing_object_is_a_problem(self, client):
        response = client.get("/api/v1/groups/999/")

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


class TestPaginationFactory:
    def test_defaults_return_base_class(self):
        assert paginated() is PagePagination

    def test_overrides_create_subclass(self):
        pagination = paginated(PaginationStyle.CURSOR, page_size=5, ordering="-id")

        assert issubclass(pagination, CursorMetaPagination)
        assert pagination.page_size == 5
        assert pagination.ordering == "-id"

    def test_ordering_is_cursor_only(self):
        from django.core.exceptions import ImproperlyConfigured

        with pytest.raises(ImproperlyConfigured):
            paginated(ordering="name")


@pytest.mark.django_db
class TestPlatformEndpoints:
    def test_liveness(self, client):
        assert client.get("/health/live/").json() == {"status": "ok"}

    def test_readiness_reports_checks(self, client):
        body = client.get("/health/ready/").json()

        assert body["status"] == "ok"
        assert set(body["checks"]) == {"database", "cache"}

    @override_settings(CORE={"HEALTH_CHECKS": ("database", "broker")})
    def test_readiness_fails_when_a_dependency_is_down(self, client, monkeypatch):
        from core.health.checks import BrokerCheck

        def fail(self):
            raise ConnectionError

        monkeypatch.setattr(BrokerCheck, "run", fail)
        response = client.get("/health/ready/")

        assert response.status_code == 503
        assert response.json()["checks"]["broker"] == {
            "healthy": False,
            "duration_ms": response.json()["checks"]["broker"]["duration_ms"],
            "error": "ConnectionError",
        }

    def test_schema_is_versioned(self, client):
        assert client.get("/api/v1/schema/").status_code == 200
        assert client.get("/api/v2/schema/").status_code == 404

    def test_unknown_routes_return_problem_json(self, client):
        response = client.get("/nope/")

        assert response.status_code == 404
        assert response["Content-Type"] == PROBLEM
