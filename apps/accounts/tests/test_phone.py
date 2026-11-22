from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.domain.phone import parse_drc_phone, phone_search_fragment
from apps.accounts.models import User
from apps.accounts.repositories import UserRepository
from apps.accounts.tests.factories import AdminFactory, ManagerFactory, UserFactory
from apps.resellers.models import ResellerApplication

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
ME = "/api/v1/me/"
APPLICATIONS = "/api/v1/bo/reseller-applications/"
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

    @pytest.mark.parametrize("term", ["081234", "81 234", "+243 81234", "0 81 234 5678"])
    def test_search_finds_partial_national_numbers(self, as_user, admin_user, term):
        UserFactory.create(phone_number="+243812345678", email="target@celebobo.test")
        UserFactory.create(phone_number="+243990000001", email="other@celebobo.test")

        body = as_user(admin_user).get(USERS, {"search": term}).json()

        assert [row["email"] for row in body["results"]] == ["target@celebobo.test"]


class TestStaffEdit:
    def test_name_of_a_client_without_phone_can_change(self, as_user, admin_user):
        user = UserFactory.create(phone_number=None)
        url = f"{USERS}{user.pk}/"

        blank = as_user(admin_user).patch(url, {"first_name": "Ruth", "phone_number": ""})
        omitted = as_user(admin_user).patch(url, {"last_name": "Tshibangu"}, format="json")
        null = as_user(admin_user).patch(url, {"phone_number": None}, format="json")

        assert blank.status_code == 200, blank.json()
        assert omitted.status_code == 200, omitted.json()
        assert null.status_code == 200, null.json()
        user.refresh_from_db()
        assert (user.first_name, user.last_name, user.phone_number) == ("Ruth", "Tshibangu", None)

    def test_a_given_phone_is_still_checked(self, as_user, admin_user):
        user = UserFactory.create(phone_number=None)

        response = as_user(admin_user).patch(f"{USERS}{user.pk}/", {"phone_number": "12345"})

        assert response.json()["code"] == "invalid_phone"

    def test_a_client_phone_cannot_be_removed(self, as_user, admin_user, client_user):
        response = as_user(admin_user).patch(
            f"{USERS}{client_user.pk}/", {"phone_number": ""}, format="json"
        )

        assert response.json()["code"] == "phone_required"


class TestConcurrentDuplicates:
    """The check passed, but another account took the number before the save."""

    TAKEN = "+243812345678"

    @pytest.fixture(autouse=True)
    def check_misses(self, monkeypatch):
        UserFactory.create(phone_number=self.TAKEN)
        monkeypatch.setattr(UserRepository, "phone_taken", lambda *_args, **_kwargs: False)

    def _assert_refused(self, response):
        assert response.status_code == 400, response.json()
        assert response.json()["code"] == "phone_already_used"
        assert "phone_number" in response.json()["errors"]

    def test_registration(self, api: APIClient):
        self._assert_refused(api.post(REGISTER, PAYLOAD))

    def test_profile(self, as_user, client_user):
        self._assert_refused(as_user(client_user).patch(ME, {"phone_number": self.TAKEN}))

    def test_staff_creation(self, as_user, admin_user):
        new = {"first_name": "Ruth", "last_name": "T", "email": "ruth@celebobo.test"}

        response = as_user(admin_user).post(
            USERS, {**new, "role": "client", "phone_number": self.TAKEN}, format="json"
        )

        self._assert_refused(response)

    def test_staff_edit(self, as_user, admin_user, client_user):
        url = f"{USERS}{client_user.pk}/"

        self._assert_refused(as_user(admin_user).patch(url, {"phone_number": self.TAKEN}))

    def test_reseller_approval(self, as_user, admin_user):
        application = ResellerApplication.objects.create(
            first_name="Grace",
            last_name="Ilunga",
            email="grace@celebobo.test",
            phone_number=self.TAKEN,
            city="Kinshasa",
        )

        response = as_user(admin_user).post(f"{APPLICATIONS}{application.pk}/approve/", {})

        self._assert_refused(response)


class TestLegacyApplications:
    """Applications sent before numbers were checked may hold a number that is not valid."""

    @pytest.fixture
    def application(self) -> ResellerApplication:
        return ResellerApplication.objects.create(
            first_name="Grace",
            last_name="Ilunga",
            email="grace@celebobo.test",
            phone_number="+33 6 12 34 56 78",
            city="Kinshasa",
        )

    def test_approved_without_the_phone(self, as_user, application):
        response = as_user(AdminFactory.create()).post(
            f"{APPLICATIONS}{application.pk}/approve/", {}
        )

        assert response.status_code == 200, response.json()
        reseller = User.objects.get(pk=response.json()["reseller_id"])
        assert reseller.role == "reseller"
        assert reseller.phone_number is None  # asked at login by the completion step
        application.refresh_from_db()
        assert application.phone_number == "+33 6 12 34 56 78"  # kept for staff to read

    def test_legacy_number_is_normalised_at_approval(self, as_user, application):
        application.phone_number = "+243 (0)82 555 0101"
        application.save(update_fields=["phone_number"])

        response = as_user(AdminFactory.create()).post(
            f"{APPLICATIONS}{application.pk}/approve/", {}
        )

        reseller = User.objects.get(pk=response.json()["reseller_id"])
        assert reseller.phone_number == "+243825550101"

    def test_search_finds_partial_national_numbers(self, as_user, application):
        application.phone_number = "+243825550101"
        application.save(update_fields=["phone_number"])

        body = as_user(AdminFactory.create()).get(APPLICATIONS, {"search": "0825550"}).json()

        assert [row["id"] for row in body["results"]] == [application.pk]


class TestParser:
    @pytest.mark.parametrize(
        "raw",
        [
            "+243 81 234 5678",
            "00243812345678",
            "243812345678",
            "0812345678",
            "812345678",
            "081.234.56-78",
            # a trunk 0 kept after the country code
            "+243 0812345678",
            "+243 (0)81 234 5678",
            "00243 0812345678",
            "2430812345678",
        ],
    )
    def test_accepted_forms(self, raw):
        assert parse_drc_phone(raw) == "+243812345678"

    @pytest.mark.parametrize(
        "raw",
        [
            "08\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668",  # Arabic-Indic digits
            "\uff10\uff18\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18",  # fullwidth digits
            "+243\u0668\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668",
            "00812345678",
            "+243 00812345678",
            "0712345678",
            "+33 6 12 34 56 78",
            "12345",
            "",
        ],
    )
    def test_rejected_forms(self, raw):
        assert parse_drc_phone(raw) is None

    @pytest.mark.parametrize(
        ("term", "fragment"),
        [
            ("081234", "81234"),
            ("+243 81 2", "812"),
            ("00243 0812", "812"),
            ("8123", "8123"),
            ("aline", None),
            ("+243", None),
            ("0", None),
            ("08\u0661\u0662", None),
        ],
    )
    def test_search_fragment(self, term, fragment):
        assert phone_search_fragment(term) == fragment


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

    def test_keeps_numbers_written_with_a_trunk_zero(self):
        user = UserFactory.create(phone_number="+243 (0)81 234 5678")

        migration.normalise_phones(apps, None)

        assert User.objects.get(pk=user.pk).phone_number == "+243812345678"
