from typing import Any

from allauth.account.models import EmailAddress
from factory.declarations import PostGeneration, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.faker import Faker

from apps.accounts.models import Address, User
from core.domain.actor import Role

DEFAULT_PASSWORD = "Kinshasa-2026!"


def _set_password(user: User, create: bool, extracted: str | None, **_: Any) -> None:
    user.set_password(extracted or DEFAULT_PASSWORD)
    if create:
        user.save(update_fields=["password"])


def _verify_email(user: User, create: bool, extracted: bool | None, **_: Any) -> None:
    if create and extracted is not False:
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = Sequence(lambda index: f"user{index}@celebobo.test")
    first_name = Faker("first_name", locale="fr_FR")
    last_name = Faker("last_name", locale="fr_FR")
    role = Role.CLIENT.value
    password = PostGeneration(_set_password)
    verified = PostGeneration(_verify_email)


class ResellerFactory(UserFactory):
    role = Role.RESELLER.value
    referral_code = Sequence(lambda index: str(4000 + index))


class ManagerFactory(UserFactory):
    role = Role.MANAGER.value
    is_staff = True


class AdminFactory(UserFactory):
    role = Role.ADMIN.value
    is_staff = True


class AddressFactory(DjangoModelFactory[Address]):
    class Meta:
        model = Address

    user = SubFactory(UserFactory)
    label = "home"
    recipient = Faker("name", locale="fr_FR")
    phone = "+243 81 234 5678"
    line1 = Sequence(lambda index: f"Avenue Lumumba n°{index}")
    quarter = "Gombe"
    city = "Kinshasa"
    country = "RD Congo"
