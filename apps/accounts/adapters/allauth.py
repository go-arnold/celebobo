from typing import Any
from urllib.parse import urlencode

from allauth.account import app_settings as account_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress, EmailConfirmation, EmailConfirmationHMAC
from allauth.account.utils import user_pk_to_url_str
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from django.conf import settings
from django.http import HttpRequest

from apps.accounts.adapters.mail import queue_message
from apps.accounts.models import User
from core.container import container

SITE_NAME = "Celebobo"
DEFAULT_FRONTEND_PATHS = {
    "email_confirmation": "/verifier-email/{key}",
    "password_reset": "/reinitialiser-mot-de-passe",
}


def frontend_url(name: str, **params: str) -> str:
    paths = {**DEFAULT_FRONTEND_PATHS, **getattr(settings, "FRONTEND_PATHS", {})}
    base = str(settings.FRONTEND_URL).rstrip("/")
    return f"{base}{paths[name].format(**params)}"


def password_reset_url(request: HttpRequest | None, user: User, temp_key: str) -> str:
    query = urlencode({"uid": user_pk_to_url_str(user), "token": temp_key})
    return f"{frontend_url('password_reset')}?{query}"


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False

    def format_email_subject(self, subject: str) -> str:
        return f"{SITE_NAME} — {subject.strip()}"

    def get_email_confirmation_url(
        self, request: HttpRequest | None, emailconfirmation: EmailConfirmation
    ) -> str:
        return frontend_url("email_confirmation", key=emailconfirmation.key)

    def send_confirmation_mail(
        self,
        request: HttpRequest | None,
        emailconfirmation: EmailConfirmation | EmailConfirmationHMAC,
        signup: bool,
    ) -> None:
        context = {
            "user": emailconfirmation.email_address.user,
            "activate_url": self.get_email_confirmation_url(request, emailconfirmation),
            "key": emailconfirmation.key,
            "site_name": SITE_NAME,
            "expiration_days": account_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS,
        }
        prefix = (
            "account/email/email_confirmation_signup"
            if signup
            else "account/email/email_confirmation"
        )
        self.send_mail(prefix, emailconfirmation.email_address.email, context)

    def send_mail(self, template_prefix: str, email: str, context: dict[str, Any]) -> None:
        context.setdefault("site_name", SITE_NAME)
        queue_message(self.render_mail(template_prefix, email, context))


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest, sociallogin: SocialLogin) -> bool:
        return True

    def save_user(self, request: HttpRequest, sociallogin: SocialLogin, form: Any = None) -> User:
        from apps.accounts.facades import AccountFacade

        user: User = super().save_user(request, sociallogin, form)
        container.resolve(AccountFacade).complete_social_signup(user.pk)
        return user


class AllauthEmailVerifier:
    def register_address(self, user: User, *, verified: bool = False) -> None:
        EmailAddress.objects.update_or_create(
            user=user,
            email=user.email,
            defaults={"primary": True, "verified": verified},
        )

    def send_verification(self, user_id: int) -> None:
        if account_settings.EMAIL_VERIFICATION == account_settings.EmailVerificationMethod.NONE:
            return
        address = (
            EmailAddress.objects.select_related("user")
            .filter(user_id=user_id, primary=True, verified=False, user__is_active=True)
            .first()
        )
        if address is not None:
            EmailConfirmationHMAC(address).send(request=None, signup=True)
