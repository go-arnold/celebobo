import pytest
from allauth.socialaccount.models import SocialAccount
from rest_framework.test import APIClient

from apps.accounts.domain.consents import (
    PRIVACY_POLICY,
    ConsentKind,
    missing_consents,
)
from apps.accounts.domain.enums import NotificationChannel, NotificationTopic
from apps.accounts.domain.events import ConsentsGiven, ConsentWithdrawn
from apps.accounts.models import Consent, User
from apps.accounts.selectors import DirectorySelector
from apps.accounts.tests.factories import (
    DEFAULT_PASSWORD,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)
from apps.content.models import Page, Subscriber
from apps.content.services.cache import ContentCache
from core.domain.actor import Role

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
ME = "/api/v1/me/"
CONSENTS = "/api/v1/me/consents/"
ADDRESSES = "/api/v1/me/addresses/"
PAYLOAD = {
    "first_name": "Aline",
    "last_name": "Mbuyi",
    "email": "aline@celebobo.test",
    "password": "Kinshasa-2026!",
    "accept_terms": True,
    "accept_hosting_abroad": True,
}
TERMS, HOSTING, MARKETING = ConsentKind.TERMS, ConsentKind.HOSTING_ABROAD, ConsentKind.MARKETING


def policy_version() -> str:
    return Page.objects.get(slug=PRIVACY_POLICY).version


def publish_policy(version: str) -> None:
    Page.objects.filter(slug=PRIVACY_POLICY).update(version=version)
    ContentCache().bump()


def open_kinds(user: User) -> set[str]:
    return set(user.consents.filter(withdrawn_at__isnull=True).values_list("kind", flat=True))


class TestMissingConsents:
    @pytest.mark.parametrize(
        ("accepted", "current", "expected"),
        [
            ({}, {}, (TERMS, HOSTING)),
            ({TERMS: "1.0"}, {TERMS: "1.0", HOSTING: "1.0"}, (HOSTING,)),
            ({TERMS: "1.0", HOSTING: "1.0"}, {TERMS: "1.0", HOSTING: "1.0"}, ()),
            # a new version of the document must be accepted again
            ({TERMS: "1.0", HOSTING: "1.0"}, {TERMS: "1.1", HOSTING: "1.0"}, (TERMS,)),
            # a document without a version accepts any
            ({TERMS: "", HOSTING: "0.9"}, {TERMS: "", HOSTING: ""}, ()),
            # marketing is never required
            ({TERMS: "1", HOSTING: "1"}, {TERMS: "1", HOSTING: "1", MARKETING: "2"}, ()),
        ],
    )
    def test_client(self, accepted, current, expected):
        assert missing_consents(Role.CLIENT, accepted, current) == expected

    @pytest.mark.parametrize("role", [Role.MANAGER, Role.ADMIN])
    def test_staff_never_have_to_consent(self, role):
        assert missing_consents(role, {}, {TERMS: "1"}) == ()

    def test_resellers_do(self):
        assert missing_consents(Role.RESELLER, {}, {}) == (TERMS, HOSTING)


class TestSignUp:
    def test_records_each_required_consent_with_version(self, api: APIClient):
        assert api.post(REGISTER, PAYLOAD).status_code == 201

        user = User.objects.get(email="aline@celebobo.test")
        rows = list(user.consents.order_by("kind").values("kind", "version", "source"))
        assert rows == [
            {"kind": "hosting_abroad", "version": policy_version(), "source": "signup"},
            {"kind": "terms", "version": policy_version(), "source": "signup"},
        ]
        assert not Subscriber.objects.exists()

    @pytest.mark.parametrize(
        ("missing", "fields"),
        [
            (("accept_terms",), {"accept_terms"}),
            (("accept_hosting_abroad",), {"accept_hosting_abroad"}),
            (("accept_terms", "accept_hosting_abroad"), {"accept_terms", "accept_hosting_abroad"}),
        ],
    )
    def test_required_boxes(self, api: APIClient, missing, fields):
        payload = {key: value for key, value in PAYLOAD.items() if key not in missing}

        response = api.post(REGISTER, payload)

        assert response.status_code == 400
        assert response.json()["code"] == "consent_required"
        assert set(response.json()["errors"]) == fields
        assert not User.objects.exists()

    def test_refused_boxes_count_as_unchecked(self, api: APIClient):
        response = api.post(REGISTER, {**PAYLOAD, "accept_hosting_abroad": False})

        assert response.json()["code"] == "consent_required"

    def test_marketing_is_optional_and_subscribes_to_the_newsletter(
        self, api: APIClient, published_events
    ):
        api.post(REGISTER, {**PAYLOAD, "accept_marketing": True})

        user = User.objects.get()
        assert open_kinds(user) == {"terms", "hosting_abroad", "marketing"}
        assert Subscriber.objects.get(email="aline@celebobo.test").is_active
        given = published_events.single(ConsentsGiven)
        assert set(given.kinds) == {TERMS, HOSTING, MARKETING}
        assert given.source == "signup"


class TestCompletionFlag:
    def test_complete_account(self, as_user, client_user):
        assert as_user(client_user).get(ME).json()["missing_consents"] == []

    def test_account_without_consents(self, as_user):
        user = UserFactory.create(consents=False)

        assert as_user(user).get(ME).json()["missing_consents"] == ["terms", "hosting_abroad"]

    def test_staff(self, as_user):
        manager = ManagerFactory.create(consents=False)

        assert as_user(manager).get(ME).json()["missing_consents"] == []

    def test_new_policy_version(self, as_user, client_user):
        publish_policy("1.0.0")

        body = as_user(client_user).get(ME).json()

        assert body["missing_consents"] == ["terms", "hosting_abroad"]


class TestGate:
    def test_incomplete_account_is_blocked(self, as_user):
        user = UserFactory.create(consents=False)

        response = as_user(user).get(ADDRESSES)

        assert response.status_code == 403
        body = response.json()
        assert body["code"] == "account_incomplete"
        assert body["meta"]["missing_consents"] == ["terms", "hosting_abroad"]

    def test_completion_endpoints_stay_reachable(self, api: APIClient):
        reseller = ResellerFactory.create(consents=False)

        login = api.post(LOGIN, {"email": reseller.email, "password": DEFAULT_PASSWORD})

        assert login.status_code == 200
        assert login.json()["user"]["missing_consents"] == ["terms", "hosting_abroad"]
        assert api.get(ME).status_code == 200
        assert api.get(CONSENTS).status_code == 200
        assert api.get("/api/v1/pages/politique-de-confidentialite/").status_code == 200
        assert api.post("/api/v1/auth/token/refresh/").status_code == 200
        assert api.post("/api/v1/auth/logout/").status_code == 200

    def test_staff_are_not_blocked(self, as_user):
        manager = ManagerFactory.create(consents=False)

        assert as_user(manager).get("/api/v1/bo/users/").status_code == 200

    def test_giving_the_consents_opens_the_account(self, as_user):
        api = as_user(UserFactory.create(consents=False))

        response = api.post(CONSENTS, {"kinds": ["terms", "hosting_abroad"]}, format="json")

        assert response.status_code == 200
        assert response.json()["missing"] == []
        assert api.get(ADDRESSES).status_code == 200


class TestGiveAndWithdraw:
    def test_overview(self, as_user, client_user):
        body = as_user(client_user).get(CONSENTS).json()

        by_kind = {item["kind"]: item for item in body["consents"]}
        assert list(by_kind) == ["terms", "hosting_abroad", "marketing"]
        assert by_kind["terms"]["given"] is True
        assert by_kind["terms"]["required"] is True
        assert by_kind["terms"]["version"] == policy_version()
        assert by_kind["terms"]["outdated"] is False
        assert by_kind["marketing"] == {
            "kind": "marketing",
            "label": "Offres commerciales par SMS, WhatsApp ou e-mail",
            "required": False,
            "given": False,
            "version": None,
            "accepted_at": None,
            "source": None,
            "current_version": policy_version(),
            "outdated": False,
        }
        assert len(body["history"]) == 2

    def test_marketing_in_one_click_both_ways(self, as_user, client_user, published_events):
        api = as_user(client_user)

        given = api.post(CONSENTS, {"kinds": ["marketing"]}, format="json").json()
        marketing = next(item for item in given["consents"] if item["kind"] == "marketing")
        assert marketing["given"] is True
        assert marketing["source"] == "account"
        assert Subscriber.objects.get(email=client_user.email).is_active

        withdrawn = api.delete(f"{CONSENTS}marketing/")
        assert withdrawn.status_code == 200
        assert "marketing" not in open_kinds(client_user)
        assert not Subscriber.objects.get(email=client_user.email).is_active
        assert published_events.single(ConsentWithdrawn).kind == MARKETING

        api.post(CONSENTS, {"kinds": ["marketing"]}, format="json")
        assert Subscriber.objects.get(email=client_user.email).is_active
        rows = client_user.consents.filter(kind="marketing")
        assert rows.count() == 2
        assert rows.filter(withdrawn_at__isnull=False).count() == 1

    def test_giving_twice_records_once(self, as_user, client_user):
        api = as_user(client_user)

        api.post(CONSENTS, {"kinds": ["terms", "terms"]}, format="json")

        assert client_user.consents.filter(kind="terms").count() == 1

    def test_new_version_is_accepted_again_and_history_kept(self, as_user, client_user):
        old = policy_version()
        publish_policy("1.0.0")
        api = as_user(client_user)

        before = api.get(CONSENTS).json()
        terms = next(item for item in before["consents"] if item["kind"] == "terms")
        assert terms["outdated"] is True
        assert api.get(ADDRESSES).status_code == 403

        after = api.post(CONSENTS, {"kinds": ["terms", "hosting_abroad"]}, format="json").json()

        assert after["missing"] == []
        versions = {(item["kind"], item["version"]) for item in after["history"]}
        assert versions == {
            ("terms", old),
            ("hosting_abroad", old),
            ("terms", "1.0.0"),
            ("hosting_abroad", "1.0.0"),
        }

    def test_withdrawing_a_required_consent_blocks_the_account(self, as_user, client_user):
        api = as_user(client_user)

        body = api.delete(f"{CONSENTS}hosting_abroad/").json()

        assert body["missing"] == ["hosting_abroad"]
        assert api.get(ADDRESSES).json()["code"] == "account_incomplete"
        # closing the account stays possible
        assert api.delete(ME).status_code == 204

    def test_unknown_kind(self, as_user, client_user):
        response = as_user(client_user).delete(f"{CONSENTS}cookies/")

        assert response.status_code == 404
        assert response.json()["code"] == "consent_not_found"

    @pytest.mark.parametrize("kinds", [[], ["cookies"]])
    def test_invalid_input(self, as_user, client_user, kinds):
        response = as_user(client_user).post(CONSENTS, {"kinds": kinds}, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == "validation_failed"

    def test_first_consents_after_google_sign_up(self, as_user):
        user = UserFactory.create(consents=False)
        SocialAccount.objects.create(user=user, provider="google", uid="google-1")
        api = as_user(user)

        api.post(CONSENTS, {"kinds": ["terms", "hosting_abroad"]}, format="json")
        api.post(CONSENTS, {"kinds": ["marketing"]}, format="json")

        sources = dict(user.consents.values_list("kind", "source"))
        assert sources == {"terms": "google", "hosting_abroad": "google", "marketing": "account"}


class TestNewsletterAndClosure:
    def test_newsletter_unsubscribe_link_withdraws_marketing(
        self, api: APIClient, as_user, client_user, django_capture_on_commit_callbacks
    ):
        as_user(client_user).post(CONSENTS, {"kinds": ["marketing"]}, format="json")
        token = str(Subscriber.objects.get(email=client_user.email).token)
        anonymous = APIClient()

        with django_capture_on_commit_callbacks(execute=True):
            response = anonymous.post(
                "/api/v1/newsletter/unsubscribe/", {"token": token}, format="json"
            )

        assert response.status_code == 204
        assert "marketing" not in open_kinds(client_user)
        assert open_kinds(client_user) == {"terms", "hosting_abroad"}

    def test_closing_the_account_withdraws_every_consent(self, as_user, client_user):
        api = as_user(client_user)
        api.post(CONSENTS, {"kinds": ["marketing"]}, format="json")

        api.delete(ME)

        assert not Consent.objects.filter(user=client_user, withdrawn_at__isnull=True).exists()
        assert Consent.objects.filter(user=client_user).count() == 3
        assert not Subscriber.objects.get(email="aline@celebobo.test").is_active


def test_promotions_only_reach_marketing_consents(as_user):
    consenting, other = UserFactory.create_batch(2)
    as_user(consenting).post(CONSENTS, {"kinds": ["marketing"]}, format="json")

    subscribed = DirectorySelector().subscribed(
        [consenting.pk, other.pk], NotificationTopic.PROMOTIONS, NotificationChannel.EMAIL
    )

    assert subscribed == {consenting.pk}
