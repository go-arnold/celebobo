from unittest.mock import Mock

import pytest
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core import mail
from django.test import RequestFactory

from apps.accounts.adapters.allauth import (
    AccountAdapter,
    AllauthEmailVerifier,
    SocialAccountAdapter,
)
from apps.accounts.domain.events import UserRegistered
from apps.accounts.handlers import send_verification_email
from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from core.domain.actor import Role

pytestmark = pytest.mark.django_db


class TestSocialSignup:
    def test_publishes_registration_without_verification_email(self, monkeypatch, published_events):
        user = UserFactory.create(verified=False)
        monkeypatch.setattr(DefaultSocialAccountAdapter, "save_user", lambda *_: user)

        saved = SocialAccountAdapter().save_user(RequestFactory().get("/"), Mock())

        event = published_events.single(UserRegistered)
        assert saved is user
        assert event.via_social is True
        send_verification_email(event)
        assert mail.outbox == []

    def test_social_signup_is_open_but_local_signup_is_closed(self):
        request = RequestFactory().get("/")

        assert SocialAccountAdapter().is_open_for_signup(request, Mock()) is True
        assert AccountAdapter().is_open_for_signup(request) is False


class TestVerificationHandler:
    def test_already_verified_users_get_no_email(self):
        user = UserFactory.create()

        send_verification_email(UserRegistered(user_id=user.pk))

        assert mail.outbox == []

    def test_unverified_users_get_one(self):
        user = UserFactory.create(verified=False)
        AllauthEmailVerifier().register_address(user)
        send_verification_email(UserRegistered(user_id=user.pk))

        assert [message.to for message in mail.outbox] == [[user.email]]


class TestUserManager:
    def test_create_superuser_is_an_admin(self):
        user = User.objects.create_superuser("Root@Celebobo.TEST", "Kinshasa-2026!")

        assert user.email == "root@celebobo.test"
        assert user.account_role is Role.ADMIN
        assert user.is_staff
        assert user.is_superuser

    def test_email_is_required(self):
        with pytest.raises(ValueError, match="email"):
            User.objects.create_user("", "Kinshasa-2026!")
