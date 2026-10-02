import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import (
    AdminFactory,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def client_user(db) -> User:
    return UserFactory.create(email="aline@celebobo.test", first_name="Aline", last_name="Mbuyi")


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create(first_name="Patrick", referral_code="4821")


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create()


@pytest.fixture
def admin_user(db) -> User:
    return AdminFactory.create()


@pytest.fixture
def as_user(api: APIClient):
    def authenticate(user: User) -> APIClient:
        api.force_authenticate(user)
        return api

    return authenticate
