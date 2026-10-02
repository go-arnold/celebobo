import pytest
import schemathesis
from django.core.signals import request_finished, request_started
from django.core.wsgi import get_wsgi_application
from django.db import close_old_connections
from hypothesis import HealthCheck, settings
from rest_framework_simplejwt.tokens import AccessToken
from schemathesis.checks import not_a_server_error
from schemathesis.specs.openapi.checks import response_schema_conformance

from apps.accounts.tests.factories import AdminFactory
from apps.catalog.tests.factories import CategoryFactory, ProductFactory

SCHEMA_URL = "/api/v1/schema/"
BACKOFFICE = r"^/api/v1/bo/"
SKIPPED_PATHS = r"(/messages/$|/download/$|/invoice/$|/export/$|/docs/|/redoc/)"
CHECKS = (not_a_server_error, response_schema_conformance)
FUZZ = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)


@pytest.fixture
def api_schema(db):
    phones = CategoryFactory.create(name="Smartphones", slug="smartphones")
    ProductFactory.create(name="Galaxy A55", slug="galaxy-a55", category=phones)
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield schemathesis.openapi.from_wsgi(SCHEMA_URL, get_wsgi_application())
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)


schema = schemathesis.pytest.from_fixture("api_schema")


@pytest.mark.django_db(transaction=False)
@schema.include(method="GET").exclude(path_regex=SKIPPED_PATHS).parametrize()
@FUZZ
def test_anonymous_reads_never_fail(case):
    case.call_and_validate(checks=CHECKS)


@pytest.mark.django_db(transaction=False)
@(
    schema.include(method="GET", path_regex=r"^/api/v1/bo/")
    .exclude(path_regex=SKIPPED_PATHS)
    .parametrize()
)
@FUZZ
def test_admin_reads_never_fail(case):
    token = AccessToken.for_user(AdminFactory.create())
    case.call_and_validate(headers={"Authorization": f"Bearer {token}"}, checks=CHECKS)
