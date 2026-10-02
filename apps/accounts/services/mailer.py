from apps.accounts.services.contracts import PasswordSetupLinks, UserStore
from core.mail import queue_templated

TEMPLATES = {
    "account_created": ("accounts/email/account_created", "Celebobo — Votre compte est prêt"),
    "password_reset": (
        "accounts/email/staff_password_reset",
        "Celebobo — Réinitialisez votre mot de passe",
    ),
}


class AccountMailer:
    def __init__(self, users: UserStore, links: PasswordSetupLinks) -> None:
        self._users = users
        self._links = links

    def account_created(self, user_id: int) -> None:
        self._send("account_created", user_id)

    def password_reset(self, user_id: int) -> None:
        self._send("password_reset", user_id)

    def _send(self, name: str, user_id: int) -> None:
        user = self._users.get(user_id)
        if user is None or not user.is_active:
            return
        template, subject = TEMPLATES[name]
        queue_templated(
            template,
            to=[user.email],
            subject=subject,
            context={"first_name": user.first_name, "url": self._links.link_for(user)},
        )
