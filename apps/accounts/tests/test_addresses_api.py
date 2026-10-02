import pytest

from apps.accounts.models import Address
from apps.accounts.services.addresses import DEFAULT_ADDRESS_LIMIT
from apps.accounts.tests.factories import AddressFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/me/addresses/"
ADDRESS = {
    "label": "home",
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Gombe",
    "city": "Kinshasa",
    "country": "RD Congo",
}


def defaults(user) -> list[int]:
    return list(Address.objects.filter(user=user, is_default=True).values_list("pk", flat=True))


class TestAddressBook:
    def test_first_address_becomes_default(self, as_user, client_user):
        response = as_user(client_user).post(URL, ADDRESS)

        assert response.status_code == 201
        assert response.json()["is_default"] is True
        assert response.json()["label"] == "home"

    def test_new_default_replaces_previous(self, as_user, client_user):
        api = as_user(client_user)
        first = api.post(URL, ADDRESS).json()
        second = api.post(URL, {**ADDRESS, "label": "office", "is_default": True}).json()

        assert defaults(client_user) == [second["id"]]
        assert [item["id"] for item in api.get(URL).json()] == [second["id"], first["id"]]

    def test_partial_update(self, as_user, client_user):
        address = AddressFactory.create(user=client_user)

        response = as_user(client_user).patch(f"{URL}{address.pk}/", {"city": "  Goma "})

        assert response.status_code == 200
        assert response.json()["city"] == "Goma"

    def test_set_default(self, as_user, client_user):
        current = AddressFactory.create(user=client_user, is_default=True)
        other = AddressFactory.create(user=client_user)

        response = as_user(client_user).post(f"{URL}{other.pk}/set-default/")

        assert response.json()["is_default"] is True
        assert defaults(client_user) == [other.pk]
        current.refresh_from_db()
        assert current.is_default is False

    def test_deleting_default_promotes_newest(self, as_user, client_user):
        default = AddressFactory.create(user=client_user, is_default=True)
        AddressFactory.create(user=client_user)
        newest = AddressFactory.create(user=client_user)

        response = as_user(client_user).delete(f"{URL}{default.pk}/")

        assert response.status_code == 204
        assert defaults(client_user) == [newest.pk]

    def test_other_users_addresses_are_invisible(self, as_user, client_user):
        foreign = AddressFactory.create(user=UserFactory.create())
        api = as_user(client_user)

        assert api.get(URL).json() == []
        assert api.patch(f"{URL}{foreign.pk}/", {"city": "Goma"}).status_code == 404
        assert api.delete(f"{URL}{foreign.pk}/").json()["code"] == "address_not_found"

    def test_book_has_a_limit(self, as_user, client_user):
        AddressFactory.create_batch(DEFAULT_ADDRESS_LIMIT, user=client_user)

        response = as_user(client_user).post(URL, ADDRESS)

        assert response.status_code == 422
        assert response.json()["code"] == "address_book_full"

    def test_validation(self, as_user, client_user):
        response = as_user(client_user).post(URL, {**ADDRESS, "label": "castle", "phone": "x"})

        assert set(response.json()["errors"]) == {"label", "phone"}


class TestPreferences:
    url = "/api/v1/me/notification-preferences/"

    def test_defaults_then_partial_update(self, as_user, client_user):
        api = as_user(client_user)

        assert api.get(self.url).json()["promotions"] == {"email": True, "push": False}

        response = api.patch(
            self.url, {"promotions": {"push": True}, "new_message": {"email": False}}
        )

        assert response.status_code == 200
        assert response.json()["promotions"] == {"email": True, "push": True}
        assert response.json()["new_message"] == {"email": False, "push": True}
        assert api.get(self.url).json() == response.json()
