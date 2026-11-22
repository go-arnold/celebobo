from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.adapters.retention import PushDevices
from apps.accounts.domain.events import AccountDeleted
from apps.accounts.models import Address, Consent, NotificationPreference, User
from apps.accounts.repositories import UserRepository
from apps.accounts.services.referrals import ReferralService
from apps.accounts.tests.factories import (
    DEFAULT_PASSWORD,
    AddressFactory,
    AdminFactory,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)
from apps.assistant.models import AssistantMessage, AssistantSession
from apps.audit.domain.retention import RetentionReport, years_before
from apps.audit.services.retention import retention_rules
from apps.catalog.models import Favorite, Product, Review
from apps.catalog.tests.factories import ProductFactory, ReviewFactory
from apps.content.models import Subscriber
from apps.documents.services.contracts import PdfRenderer
from apps.loyalty.models import PointsEntry
from apps.media.models import UploadedMedia
from apps.media.services.contracts import MediaStorage
from apps.messaging.models import Conversation, Message, Notification
from apps.orders.models import Order, OrderRating
from apps.orders.tests.conftest import ADDRESS, api, as_user, phone, place_order
from apps.push.models import PushSubscription
from apps.resellers.models import ResellerApplication
from core.container import container
from core.events.contracts import EventPublisher
from core.testing.fakes import RecordingPublisher

__all__ = ["api", "as_user", "phone", "place_order"]

pytestmark = pytest.mark.django_db

RULE = "accounts.inactive_clients"
NOW = timezone.now()
CUTOFF = years_before(NOW, 3)
LONG_AGO = CUTOFF - timedelta(days=30)


def apply(*, dry_run: bool = False, now: datetime = NOW) -> RetentionReport:
    return retention_rules.create(RULE).apply(now=now, dry_run=dry_run)


def quiet(user: User, *, seen: datetime = LONG_AGO) -> User:
    User.objects.filter(pk=user.pk).update(date_joined=seen, last_login=seen)
    user.refresh_from_db()
    return user


def anonymized(user: User) -> bool:
    user.refresh_from_db()
    return user.deleted_at is not None


@pytest.fixture
def sleeper(db) -> User:
    return quiet(
        UserFactory.create(
            email="aline@celebobo.test",
            first_name="Aline",
            last_name="Mbuyi",
            phone_number="+243 81 000 0001",
            avatar="https://cdn.celebobo.test/aline.jpg",
        )
    )


def old_order(place_order, user: User, product, *, at: datetime = LONG_AGO) -> Order:
    order = Order.objects.get(number=place_order(user, product, note="Sonner deux fois")["number"])
    Order.objects.filter(pk=order.pk).update(created_at=at)
    Conversation.objects.filter(order=order).update(created_at=at, last_message_at=None)
    Message.objects.filter(conversation__order=order).update(created_at=at)
    PointsEntry.objects.filter(user=user).update(created_at=at)
    quiet(user)
    return Order.objects.get(pk=order.pk)


class TestWhatIsWiped:
    def test_identity_and_account_data_go(self, sleeper, published_events):
        AddressFactory.create(user=sleeper)
        NotificationPreference.objects.create(user=sleeper, preferences={"orders": {}})
        SocialAccount.objects.create(user=sleeper, provider="google", uid="g-1")
        PushSubscription.objects.create(
            user=sleeper, endpoint="https://push.test/1", p256dh="k", auth="a"
        )
        RefreshToken.for_user(sleeper)
        OutstandingToken.objects.filter(user=sleeper).update(created_at=LONG_AGO)

        report = apply()

        user = User.objects.get(pk=sleeper.pk)
        assert report.affected == 1
        assert user.email == f"deleted-{user.pk}@deleted.invalid"
        assert (user.first_name, user.last_name, user.avatar, user.phone_number) == (
            "",
            "",
            "",
            None,
        )
        assert user.is_active is False
        assert user.deleted_at is not None
        assert not user.has_usable_password()
        assert not Address.objects.filter(user=user).exists()
        assert not NotificationPreference.objects.filter(user=user).exists()
        assert not EmailAddress.objects.filter(user=user).exists()
        assert not SocialAccount.objects.filter(user=user).exists()
        assert not PushSubscription.objects.filter(user=user).exists()
        assert all(
            hasattr(token, "blacklistedtoken")
            for token in OutstandingToken.objects.filter(user=user)
        )
        event = published_events.single(AccountDeleted)
        assert (event.user_id, event.inactivity, event.actor_id) == (user.pk, True, None)

    def test_placeholders_stay_unique(self, db):
        first, second = (quiet(UserFactory.create(phone_number=f"+24381000000{i}")) for i in (1, 2))

        assert apply().affected == 2

        emails = set(User.objects.filter(pk__in=[first.pk, second.pk]).values_list("email"))
        assert len(emails) == 2

    def test_the_client_can_no_longer_log_in(self, api, sleeper):
        apply()

        response = api.post(
            "/api/v1/auth/login/", {"email": "aline@celebobo.test", "password": DEFAULT_PASSWORD}
        )

        assert response.status_code == 400

    def test_orders_stay_without_contact_details(self, sleeper, phone, place_order):
        order = old_order(place_order, sleeper, phone)
        Message.objects.create(
            conversation=Conversation.objects.get(order=order), sender=sleeper, body="Bonjour"
        )
        Message.objects.filter(sender=sleeper).update(created_at=LONG_AGO)
        OrderRating.objects.create(
            order=order, reseller=ResellerFactory.create(), client=sleeper, score=5, comment="Top"
        )
        PointsEntry.objects.create(
            user=sleeper, order=order, kind="earn", amount=Decimal(1), available_at=LONG_AGO
        )
        PointsEntry.objects.filter(user=sleeper).update(created_at=LONG_AGO)

        assert apply().affected == 1

        order.refresh_from_db()
        assert (order.phone, order.note, order.delivery_code) == ("", "", "")
        # the invoice keeps the delivery recipient and address (accounting, 10 years)
        assert (order.recipient, order.line1, order.city) == (
            ADDRESS["recipient"],
            ADDRESS["line1"],
            ADDRESS["city"],
        )
        assert order.total > 0
        assert OrderRating.objects.get(order=order).comment == ""
        assert not PointsEntry.objects.filter(user=sleeper).exists()
        assert not Conversation.objects.filter(client=sleeper).exists()
        assert not Notification.objects.filter(recipient=sleeper).exists()

    def test_referral_link_is_kept(self, sleeper):
        reseller = ResellerFactory.create()
        User.objects.filter(pk=sleeper.pk).update(invited_by=reseller)

        apply()

        sleeper.refresh_from_db()
        assert sleeper.invited_by_id == reseller.pk


class TestThreshold:
    @pytest.mark.parametrize(
        ("offset", "expected"),
        [(timedelta(minutes=-1), True), (timedelta(minutes=1), False)],
        ids=["just-after-3-years", "just-before-3-years"],
    )
    def test_last_login(self, sleeper, offset, expected):
        quiet(sleeper, seen=CUTOFF + offset)

        apply()

        assert anonymized(sleeper) is expected

    def test_never_logged_in_counts_from_sign_up(self, db):
        user = UserFactory.create()
        User.objects.filter(pk=user.pk).update(date_joined=LONG_AGO, last_login=None)

        apply()

        assert anonymized(user)

    def test_recent_sign_up_without_login_is_kept(self, db):
        user = UserFactory.create()
        User.objects.filter(pk=user.pk).update(last_login=None)

        apply()

        assert not anonymized(user)


class TestOtherActivity:
    @pytest.mark.parametrize(
        ("at", "expected"),
        [(CUTOFF - timedelta(minutes=1), True), (CUTOFF + timedelta(minutes=1), False)],
        ids=["order-just-over-3-years", "order-just-under-3-years"],
    )
    def test_last_order(self, sleeper, phone, place_order, at, expected):
        old_order(place_order, sleeper, phone, at=at)

        apply()

        assert anonymized(sleeper) is expected

    def test_recent_message_keeps_the_account(self, sleeper, phone, place_order):
        order = old_order(place_order, sleeper, phone)
        Message.objects.create(
            conversation=Conversation.objects.get(order=order), sender=sleeper, body="Toujours là"
        )

        apply()

        assert not anonymized(sleeper)

    def test_recent_points_movement_keeps_the_account(self, sleeper):
        PointsEntry.objects.create(user=sleeper, kind="spend", amount=Decimal(-1), available_at=NOW)

        apply()

        assert not anonymized(sleeper)

    def test_points_expiry_is_not_activity(self, sleeper):
        PointsEntry.objects.create(
            user=sleeper, kind="expiry", amount=Decimal(-1), available_at=NOW
        )

        apply()

        assert anonymized(sleeper)

    def test_session_renewal_keeps_the_account(self, sleeper):
        RefreshToken.for_user(sleeper)

        apply()

        assert not anonymized(sleeper)


class TestExclusions:
    @pytest.mark.parametrize(
        "make",
        [
            ManagerFactory.create,
            ResellerFactory.create,
            # a former reseller back to client keeps their code and their commission records
            lambda: UserFactory.create(referral_code="7777"),
            lambda: UserFactory.create(is_superuser=True),
        ],
        ids=["staff", "reseller", "former-reseller", "superuser"],
    )
    def test_staff_and_resellers_are_never_anonymised(self, db, make):
        user = quiet(make())

        apply()

        assert not anonymized(user)
        assert user.email == User.objects.get(pk=user.pk).email


class TestRuns:
    def test_idempotent(self, sleeper, published_events):
        assert apply().affected == 1
        deleted_at = User.objects.get(pk=sleeper.pk).deleted_at

        again = apply(now=NOW + timedelta(days=1))

        assert again.affected == 0
        assert User.objects.get(pk=sleeper.pk).deleted_at == deleted_at
        assert len(published_events.of_type(AccountDeleted)) == 1

    def test_dry_run_changes_nothing(self, sleeper, published_events):
        report = apply(dry_run=True)

        assert report.affected == 1
        assert report.dry_run is True
        assert report.samples == (
            f"compte client #{sleeper.pk}, vu pour la dernière fois le {LONG_AGO:%Y-%m-%d}",
        )
        assert not anonymized(sleeper)
        assert published_events.of_type(AccountDeleted) == []

    def test_batches_skip_the_accounts_kept(self, db, monkeypatch, phone, place_order):
        monkeypatch.setattr("apps.accounts.facades.BATCH_SIZE", 2)
        users = [quiet(UserFactory.create()) for _ in range(5)]
        old_order(place_order, users[0], phone, at=NOW)
        old_order(place_order, users[1], phone, at=NOW)

        report = apply()

        assert report.affected == 3
        assert [anonymized(user) for user in users] == [False, False, True, True, True]


class TestAnonymisedAccountsDoNotBreak:
    @pytest.fixture
    def order(self, sleeper, phone, place_order) -> Order:
        order = old_order(place_order, sleeper, phone)
        apply()
        return order

    def test_staff_order_pages(self, as_user, order):
        manager = ManagerFactory.create()

        detail = as_user(manager).get(f"/api/v1/bo/orders/{order.pk}/")
        page = as_user(manager).get("/api/v1/bo/orders/")

        assert detail.status_code == 200
        assert detail.json()["client"]["name"] == "Client anonymisé"
        assert detail.json()["client"]["email"] is None
        assert page.status_code == 200
        assert page.json()["results"][0]["client_name"] == "Client anonymisé"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/bo/dashboard/summary/",
            "/api/v1/bo/dashboard/recent-sales/",
            "/api/v1/bo/dashboard/open-orders/",
            "/api/v1/bo/analytics/sellers/",
        ],
    )
    def test_analytics(self, as_user, order, path):
        assert as_user(AdminFactory.create()).get(path).status_code == 200

    def test_invoice_keeps_the_recipient_but_no_account_contact(self, as_user, order):
        rendered: list[str] = []

        class HtmlRenderer:
            def render(self, template: str, context: Mapping[str, Any]) -> bytes:
                rendered.append(render_to_string(template, dict(context)))
                return b"%PDF-fake"

        with container.override(PdfRenderer, HtmlRenderer()):
            response = as_user(ManagerFactory.create()).get(
                f"/api/v1/bo/orders/{order.pk}/invoice/"
            )

        assert response.status_code == 200
        assert ADDRESS["recipient"] in rendered[0]
        assert "deleted.invalid" not in rendered[0]
        assert "Client anonymisé" in rendered[0]

    def test_reseller_invitees(self, as_user, order, sleeper):
        reseller = ResellerFactory.create()
        User.objects.filter(pk=sleeper.pk).update(invited_by=reseller)

        response = as_user(reseller).get("/api/v1/bo/me/invitees/")

        assert response.status_code == 200


def self_delete(as_user, user: User, *, at: datetime = LONG_AGO) -> User:
    assert as_user(user).delete("/api/v1/me/").status_code == 204
    User.objects.filter(pk=user.pk).update(deleted_at=at)
    user.refresh_from_db()
    return user


def erased(user: User) -> bool:
    user.refresh_from_db()
    return user.personal_data_erased_at is not None


class TestSelfDeletedAccounts:
    def test_what_the_identity_scrub_left_goes_3_years_later(
        self, as_user, sleeper, phone, place_order
    ):
        order = old_order(place_order, sleeper, phone)
        OrderRating.objects.create(
            order=order, reseller=ResellerFactory.create(), client=sleeper, score=4, comment="Bien"
        )
        PointsEntry.objects.create(
            user=sleeper, order=order, kind="earn", amount=Decimal(1), available_at=LONG_AGO
        )
        PointsEntry.objects.filter(user=sleeper).update(created_at=LONG_AGO)
        deleted_on = self_delete(as_user, sleeper).deleted_at

        publisher = RecordingPublisher()
        with container.override(EventPublisher, publisher):
            report = apply()

        order.refresh_from_db()
        user = User.objects.get(pk=sleeper.pk)
        assert report.affected == 1
        assert (order.phone, order.note, order.delivery_code) == ("", "", "")
        assert OrderRating.objects.get(order=order).comment == ""
        assert not PointsEntry.objects.filter(user=sleeper).exists()
        assert not Conversation.objects.filter(client=sleeper).exists()
        # the deletion itself is unchanged and not announced again
        assert user.deleted_at == deleted_on
        assert user.personal_data_erased_at is not None
        assert publisher.of_type(AccountDeleted) == []

    def test_dry_run_describes_the_deletion(self, as_user, sleeper):
        self_delete(as_user, sleeper)

        report = apply(dry_run=True)

        assert report.samples == (f"compte client #{sleeper.pk}, supprimé le {LONG_AGO:%Y-%m-%d}",)
        assert not erased(sleeper)

    @pytest.mark.parametrize(
        ("offset", "expected"),
        [(timedelta(minutes=-1), True), (timedelta(minutes=1), False)],
        ids=["deleted-just-over-3-years", "deleted-just-under-3-years"],
    )
    def test_threshold_runs_from_the_deletion(self, as_user, sleeper, offset, expected):
        self_delete(as_user, sleeper, at=CUTOFF + offset)

        apply()

        assert erased(sleeper) is expected

    def test_processed_once(self, as_user, sleeper):
        self_delete(as_user, sleeper)
        assert apply().affected == 1
        marked = User.objects.get(pk=sleeper.pk).personal_data_erased_at

        assert apply(now=NOW + timedelta(days=1)).affected == 0
        assert User.objects.get(pk=sleeper.pk).personal_data_erased_at == marked

    def test_accounts_anonymised_for_inactivity_are_not_processed_again(self, sleeper):
        assert apply().affected == 1

        assert apply(now=NOW + timedelta(days=4 * 365)).affected == 0

    def test_a_former_reseller_who_deleted_their_account_is_cleaned_too(
        self, as_user, phone, place_order
    ):
        former = UserFactory.create(referral_code="4321")
        old_order(place_order, former, phone)
        self_delete(as_user, former)

        assert apply().affected == 1
        assert Order.objects.get(client=former).phone == ""


class TestMoreErasers:
    def test_assistant_conversations_go(self, sleeper):
        session = AssistantSession.objects.create(user=sleeper, title="Quel téléphone ?")
        AssistantMessage.objects.create(session=session, role="user", content="Je cherche")
        anonymous = AssistantSession.objects.create(user=None)

        apply()

        assert not AssistantSession.objects.filter(pk=session.pk).exists()
        assert not AssistantMessage.objects.filter(session_id=session.pk).exists()
        assert AssistantSession.objects.filter(pk=anonymous.pk).exists()

    def test_reseller_applications_go_unless_approved(self, sleeper):
        def application(status: str) -> ResellerApplication:
            return ResellerApplication.objects.create(
                first_name="Aline",
                last_name="Mbuyi",
                email=f"aline-{status}@celebobo.test",
                phone_number="+243 81 000 0001",
                city="Kinshasa",
                status=status,
                applicant=sleeper,
            )

        application("pending")
        application("rejected")
        approved = application("approved")

        apply()

        assert set(ResellerApplication.objects.values_list("pk", flat=True)) == {approved.pk}

    def test_favourites_and_reviews_go(self, sleeper):
        product = ProductFactory.create()
        Favorite.objects.create(user=sleeper, product=product)
        ReviewFactory.create(user=sleeper, product=product, rating=1)
        ReviewFactory.create(user=UserFactory.create(), product=product, rating=5)
        Product.all_objects.filter(pk=product.pk).update(rating_avg=Decimal(3), reviews_count=2)

        apply()

        assert not Favorite.objects.filter(user=sleeper).exists()
        assert not Review.objects.filter(user=sleeper).exists()
        product = Product.all_objects.get(pk=product.pk)
        assert (product.rating_avg, product.reviews_count) == (Decimal("5.00"), 1)

    def test_uploaded_avatar_and_attachments_are_destroyed(self, sleeper):
        destroyed: list[str] = []

        class RecordingStorage:
            def destroy(self, public_id: str) -> None:
                destroyed.append(public_id)

        def upload(owner: User, name: str, purpose: str) -> UploadedMedia:
            return UploadedMedia.objects.create(
                owner=owner,
                purpose=purpose,
                public_id=f"celebobo/{purpose}/{name}",
                url=f"https://res.cloudinary.com/demo/image/upload/v1/{name}.jpg",
                format="jpg",
                bytes=1000,
            )

        avatar = upload(sleeper, "aline", "avatar")
        attachment = upload(sleeper, "receipt", "message_attachment")
        User.objects.filter(pk=sleeper.pk).update(avatar=avatar.url)
        others = upload(UserFactory.create(), "grace", "avatar")

        with container.override(MediaStorage, RecordingStorage()):
            apply()

        assert sorted(destroyed) == sorted([avatar.public_id, attachment.public_id])
        assert not UploadedMedia.objects.filter(owner=sleeper).exists()
        assert UploadedMedia.objects.filter(pk=others.pk).exists()


class TestNewsletter:
    def test_the_subscription_of_the_account_e_mail_goes(self, sleeper):
        Subscriber.objects.create(email="ALINE@celebobo.test")
        Subscriber.objects.create(email="grace@celebobo.test")

        apply()

        assert list(Subscriber.objects.values_list("email", flat=True)) == ["grace@celebobo.test"]

    def test_an_opposition_already_expressed_stays(self, sleeper):
        Subscriber.objects.create(email="aline@celebobo.test", unsubscribed_at=LONG_AGO)

        apply()

        assert Subscriber.objects.filter(email="aline@celebobo.test").exists()

    def test_deleting_the_account_ends_the_subscription(self, as_user, sleeper):
        Subscriber.objects.create(email="aline@celebobo.test")

        assert as_user(sleeper).delete("/api/v1/me/").status_code == 204

        assert not Subscriber.objects.exists()

    def test_deleting_an_account_with_marketing_accepted_drops_the_address(self, as_user, sleeper):
        # withdrawing the consent on deletion must not turn the row into an opposition kept forever
        Consent.objects.create(
            user=sleeper,
            kind="marketing",
            version="0.9.2",
            source="signup",
            accepted_at=timezone.now(),
        )
        Subscriber.objects.create(email="aline@celebobo.test")

        assert as_user(sleeper).delete("/api/v1/me/").status_code == 204

        assert not Subscriber.objects.exists()
        consent = Consent.objects.get(user=sleeper, kind="marketing")
        assert consent.withdrawn_at is not None

    def test_deleting_the_account_keeps_the_opposition(self, as_user, sleeper):
        Subscriber.objects.create(email="aline@celebobo.test", unsubscribed_at=LONG_AGO)

        assert as_user(sleeper).delete("/api/v1/me/").status_code == 204

        assert Subscriber.objects.filter(email="aline@celebobo.test").exists()


class TestFailures:
    def test_one_failing_account_does_not_block_the_others(self, db, monkeypatch):
        users = [quiet(UserFactory.create()) for _ in range(3)]
        failing = users[1]
        erase = PushDevices.erase

        def flaky(self: PushDevices, user_id: int) -> None:
            if user_id == failing.pk:
                raise RuntimeError("push service down")
            erase(self, user_id)

        monkeypatch.setattr(PushDevices, "erase", flaky)

        report = apply()

        assert report.affected == 2
        assert [anonymized(user) for user in users] == [True, False, True]
        # rolled back entirely: the failing account is retried on the next run
        assert User.objects.get(pk=failing.pk).email == failing.email

        monkeypatch.setattr(PushDevices, "erase", erase)
        assert apply().affected == 1
        assert anonymized(failing)


class TestReferralCodes:
    def test_a_former_reseller_s_code_is_never_reissued(self, as_user, db):
        former = UserFactory.create(referral_code="4321")

        assert as_user(former).delete("/api/v1/me/").status_code == 204

        former.refresh_from_db()
        assert former.deleted_at is not None
        assert former.referral_code == "4321"
        codes = iter(["4321", "1234"])
        service = ReferralService(UserRepository(), generate=lambda: next(codes))
        assert service.issue_code() == "1234"
