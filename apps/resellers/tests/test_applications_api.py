from decimal import Decimal

import pytest
from allauth.account.models import EmailAddress

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.resellers.domain.events import ApplicationApproved, ApplicationSubmitted
from apps.resellers.models import ResellerApplication
from apps.resellers.tests.conftest import APPLICATION

pytestmark = pytest.mark.django_db

PUBLIC = "/api/v1/reseller-applications/"
BO = "/api/v1/bo/reseller-applications/"


@pytest.fixture
def application(api) -> ResellerApplication:
    response = api.post(PUBLIC, APPLICATION, format="json")
    assert response.status_code == 201, response.json()
    return ResellerApplication.objects.get(pk=response.json()["id"])


class TestSubmission:
    def test_anyone_can_apply(self, api, published_events):
        response = api.post(PUBLIC, APPLICATION, format="json")

        assert response.status_code == 201
        assert response.json()["status"] == "pending"
        stored = ResellerApplication.objects.get()
        assert stored.email == "grace.ilunga@example.com"
        assert stored.first_name == "Grâce"
        assert stored.applicant_id is None
        assert any(isinstance(event, ApplicationSubmitted) for event in published_events.events)

    def test_signed_in_applicants_are_linked(self, as_user, shopper):
        as_user(shopper).post(PUBLIC, APPLICATION, format="json")

        assert ResellerApplication.objects.get().applicant_id == shopper.pk

    def test_one_pending_application_per_email(self, api, application):
        again = api.post(
            PUBLIC, {**APPLICATION, "email": "GRACE.ilunga@example.com"}, format="json"
        )

        assert again.status_code == 409
        assert again.json()["code"] == "application_pending"

    def test_resellers_cannot_apply(self, api, reseller):
        response = api.post(PUBLIC, {**APPLICATION, "email": reseller.email}, format="json")

        assert response.status_code == 409
        assert response.json()["code"] == "already_reseller"

    def test_validates_the_form(self, api):
        response = api.post(PUBLIC, {**APPLICATION, "phone_number": "abc"}, format="json")

        assert response.status_code == 400
        assert "phone_number" in response.json()["errors"]

    def test_acknowledges_by_email(self, api, mailoutbox, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            api.post(PUBLIC, APPLICATION, format="json")

        (mail,) = mailoutbox
        assert mail.to == ["grace.ilunga@example.com"]
        assert "Bonjour Grâce" in mail.body


class TestReview:
    def test_listing_with_counts_and_filters(self, as_user, manager, application):
        api = as_user(manager)

        body = api.get(BO).json()
        rejected = api.get(BO, {"status": "rejected"}).json()
        searched = api.get(BO, {"search": "lubumbashi"}).json()

        assert body["meta"]["count"] == 1
        assert body["meta"]["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
        assert body["results"][0]["message"].startswith("Je vends")
        assert rejected["meta"]["count"] == 0
        assert searched["meta"]["count"] == 1
        assert api.get(f"{BO}{application.pk}/").json()["city"] == "Lubumbashi"

    def test_approval_creates_a_reseller_account(
        self, as_user, manager, application, published_events
    ):
        response = as_user(manager).post(
            f"{BO}{application.pk}/approve/",
            {"commission_rate": "0.120", "manager_id": manager.pk},
            format="json",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert body["reviewed_by"]["id"] == manager.pk
        user = User.objects.get(pk=body["reseller_id"])
        assert user.role == "reseller"
        assert user.email == "grace.ilunga@example.com"
        assert user.phone_number == "+243 82 555 0101"
        assert user.commission_rate == Decimal("0.120")
        assert user.manager_id == manager.pk
        assert user.referral_code is not None
        assert len(user.referral_code) == 4
        assert not user.has_usable_password()
        assert EmailAddress.objects.get(user=user).verified
        approved = next(e for e in published_events.events if isinstance(e, ApplicationApproved))
        assert approved.account_created is True

    def test_approval_promotes_an_existing_client(self, as_user, manager, shopper, api):
        api.post(PUBLIC, {**APPLICATION, "email": shopper.email}, format="json")
        application = ResellerApplication.objects.get()

        as_user(manager).post(f"{BO}{application.pk}/approve/", {}, format="json")

        shopper.refresh_from_db()
        assert shopper.role == "reseller"
        assert shopper.commission_rate == Decimal("0.070")
        assert shopper.has_usable_password()

    def test_staff_emails_cannot_be_approved(self, as_user, manager, api):
        staff = UserFactory.create(role="admin")
        api.post(PUBLIC, {**APPLICATION, "email": staff.email}, format="json")
        application = ResellerApplication.objects.get()

        response = as_user(manager).post(f"{BO}{application.pk}/approve/", {}, format="json")

        assert response.status_code == 422
        application.refresh_from_db()
        assert application.status == "pending"

    def test_rejects_invalid_managers(self, as_user, manager, shopper, application):
        response = as_user(manager).post(
            f"{BO}{application.pk}/approve/", {"manager_id": shopper.pk}, format="json"
        )

        assert response.status_code == 400
        assert "manager_id" in response.json()["errors"]

    def test_approval_email_carries_the_password_setup_link(
        self, as_user, manager, application, mailoutbox, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            as_user(manager).post(f"{BO}{application.pk}/approve/", {}, format="json")

        (mail,) = mailoutbox
        assert "Choisissez votre mot de passe" in mail.body
        assert "/reinitialiser-mot-de-passe?uid=" in mail.body

    def test_rejection(
        self, as_user, manager, application, mailoutbox, django_capture_on_commit_callbacks
    ):
        api = as_user(manager)
        with django_capture_on_commit_callbacks(execute=True):
            response = api.post(
                f"{BO}{application.pk}/reject/", {"reason": "Zone déjà couverte"}, format="json"
            )
        again = api.post(f"{BO}{application.pk}/approve/", {}, format="json")

        assert response.json()["status"] == "rejected"
        assert response.json()["decision_note"] == "Zone déjà couverte"
        assert "Motif : Zone déjà couverte" in mailoutbox[0].body
        assert again.status_code == 409
        assert not User.objects.filter(email=application.email).exists()

    def test_rejected_applicants_can_apply_again(self, as_user, manager, api, application):
        as_user(manager).post(f"{BO}{application.pk}/reject/", {}, format="json")
        api.force_authenticate(None)

        assert api.post(PUBLIC, APPLICATION, format="json").status_code == 201

    def test_only_staff_review(self, as_user, reseller, application):
        api = as_user(reseller)

        assert api.get(BO).status_code == 403
        assert api.post(f"{BO}{application.pk}/approve/", {}, format="json").status_code == 403

    def test_unknown_application(self, as_user, manager):
        assert as_user(manager).get(f"{BO}999999/").status_code == 404
