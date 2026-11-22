from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import ManagerFactory, UserFactory

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
ME = "/api/v1/me/"
ADDRESSES = "/api/v1/me/addresses/"
USERS = "/api/v1/bo/users/"
PAYLOAD = {
    "first_name": "Aline",
    "last_name": "Mbuyi",
    "email": "aline@celebobo.test",
    "password": "Kinshasa-2026!",
    "phone_number": "081 234 5678",
    "accept_terms": True,
    "accept_hosting_abroad": True,
}

migration = import_module("apps.accounts.migrations.0005_phone_number_e164")


class TestSignUp:
    def test_stores_the_e164_form(self, api: APIClient):
        assert api.post(REGISTER, PAYLOAD).status_code == 201

        assert User.objects.get().phone_number == "+243812345678"

    @pytest.mark.parametrize(
        ("phone", "code"),
        [(None, "phone_required"), ("", "phone_required"), ("12345", "invalid_phone")],
    )
    def test_rejections(self, api: APIClient, phone, code):
        payload = {**PAYLOAD, "phone_number": phone} if phone is not None else {**PAYLOAD}
        if phone is None:
            payload.pop("phone_number")

        response = api.post(REGISTER, payload, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == code
        assert "phone_number" in response.json()["errors"]

    def test_one_account_per_phone_whatever_the_format(self, api: APIClient):
        UserFactory.create(phone_number="+243812345678")

        response = api.post(REGISTER, {**PAYLOAD, "phone_number": "00243 812 345 678"})

        assert response.status_code == 400
        assert response.json()["code"] == "phone_already_used"


class TestCompletion:
    def test_account_without_phone_must_complete(self, as_user):
        user = UserFactory.create(phone_number=None)
        api = as_user(user)

        assert api.get(ME).json()["phone_required"] is True
        blocked = api.get(ADDRESSES)
        assert blocked.status_code == 403
        assert blocked.json()["meta"] == {"missing_consents": [], "phone_required": True}

        completed = api.patch(ME, {"phone_number": "0997 000 111"})

        assert completed.json()["phone_required"] is False
        assert completed.json()["phone_number"] == "+243997000111"
        user.refresh_from_db()  # a real request loads the account again
        api.force_authenticate(user)
        assert api.get(ADDRESSES).status_code == 200

    def test_staff_need_no_phone(self, as_user):
        api = as_user(ManagerFactory.create(phone_number=None))

        assert api.get(ME).json()["phone_required"] is False
        assert api.get(USERS).status_code == 200

    def test_clients_cannot_remove_their_phone(self, as_user, client_user):
        response = as_user(client_user).patch(ME, {"phone_number": None}, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == "phone_required"

    def test_staff_can(self, as_user, manager):
        response = as_user(manager).patch(ME, {"phone_number": None}, format="json")

        assert response.json()["phone_number"] is None

    def test_invalid_phone_on_profile(self, as_user, client_user):
        response = as_user(client_user).patch(ME, {"phone_number": "+33 6 12 34 56 78"})

        assert response.json()["code"] == "invalid_phone"


class TestStaffCreation:
    def test_clients_and_resellers_need_a_phone(self, as_user, admin_user):
        new = {"first_name": "Ruth", "last_name": "Tshibangu", "email": "ruth@celebobo.test"}

        client = as_user(admin_user).post(USERS, {**new, "role": "client"}, format="json")
        manager = as_user(admin_user).post(USERS, {**new, "role": "manager"}, format="json")

        assert client.json()["code"] == "phone_required"
        assert manager.status_code == 201
        assert manager.json()["phone_number"] is None

    def test_search_finds_local_formats(self, as_user, admin_user):
        UserFactory.create(phone_number="+243812345678", email="target@celebobo.test")

        body = as_user(admin_user).get(USERS, {"search": "0812345678"}).json()

        assert [row["email"] for row in body["results"]] == ["target@celebobo.test"]


class TestDatabase:
    def test_phone_is_unique(self):
        UserFactory.create(phone_number="+243812345678")

        with pytest.raises(IntegrityError), transaction.atomic():
            UserFactory.create(phone_number="+243812345678")

    def test_many_accounts_without_phone(self):
        UserFactory.create_batch(2, phone_number=None)
        ManagerFactory.create_batch(2, phone_number="")

        assert User.objects.filter(phone_number__isnull=True).count() == 2


class TestMigration:
    def test_normalises_and_keeps_the_most_recently_active(self):
        now = timezone.now()
        old = UserFactory.create(phone_number="0812345678", last_login=now - timedelta(days=30))
        recent = UserFactory.create(phone_number="+243 81 234 5678", last_login=now)
        seen = UserFactory.create(phone_number="099-000-0001", last_seen_at=now)
        twin = UserFactory.create(phone_number="+243990000001", date_joined=now - timedelta(days=1))
        invalid = UserFactory.create(phone_number="12345")
        empty = ManagerFactory.create(phone_number="")

        migration.normalise_phones(apps, None)

        phones = dict(User.objects.values_list("pk", "phone_number"))
        assert phones[recent.pk] == "+243812345678"
        assert phones[old.pk] is None
        # seen today beats an account only known by its sign-up, yesterday
        assert phones[seen.pk] == "+243990000001"
        assert phones[twin.pk] is None
        assert phones[invalid.pk] is None
        assert phones[empty.pk] is None

    def test_ties_go_to_the_newest_account(self):
        joined = timezone.now() - timedelta(days=3)
        first = UserFactory.create(phone_number="0812345678", date_joined=joined)
        second = UserFactory.create(phone_number="812345678", date_joined=joined)

        migration.normalise_phones(apps, None)

        assert User.objects.get(pk=second.pk).phone_number == "+243812345678"
        assert User.objects.get(pk=first.pk).phone_number is None
