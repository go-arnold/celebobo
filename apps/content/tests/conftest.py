import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory, ManagerFactory, ResellerFactory
from apps.content.models import SiteSettings
from apps.orders.tests.conftest import api, as_user

__all__ = ["api", "as_user"]


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create(first_name="Joël", last_name="Mpiana")


@pytest.fixture
def admin(db) -> User:
    return AdminFactory.create()


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create()


@pytest.fixture
def site(db) -> SiteSettings:
    settings, _ = SiteSettings.objects.update_or_create(
        pk=1,
        defaults={
            "hotline": "+243 81 000 0000",
            "whatsapp": "+243 82 111 2222",
            "email": "support@celebobo.test",
            "newsletter_code": "BIENVENUE10",
            "newsletter_discount": 10,
            "payment_methods": ["orange_money", "cash"],
        },
    )
    return settings
