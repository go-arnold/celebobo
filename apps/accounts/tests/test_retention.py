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

from apps.accounts.domain.events import AccountDeleted
from apps.accounts.models import Address, NotificationPreference, User
from apps.accounts.tests.factories import (
    DEFAULT_PASSWORD,
    AddressFactory,
    AdminFactory,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)
from apps.audit.domain.retention import RetentionReport, years_before
from apps.audit.services.retention import retention_rules
from apps.documents.services.contracts import PdfRenderer
from apps.loyalty.models import PointsEntry
from apps.messaging.models import Conversation, Message, Notification
from apps.orders.models import Order, OrderRating
from apps.orders.tests.conftest import ADDRESS, api, as_user, phone, place_order
from apps.push.models import PushSubscription
from core.container import container

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
