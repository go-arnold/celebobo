from apps.resellers.domain.read_models import ApplicationView
from apps.resellers.services.contracts import ResellerAccounts
from core.mail import queue_templated

TEMPLATES = "resellers/email/application_{name}"
SUBJECTS = {
    "received": "Celebobo — Candidature reçue",
    "approved": "Celebobo — Bienvenue dans le programme revendeur",
    "rejected": "Celebobo — Votre candidature revendeur",
}


class ApplicationMailer:
    def __init__(self, accounts: ResellerAccounts, *, base_url: str, login_path: str) -> None:
        self._accounts = accounts
        self._base_url = base_url.rstrip("/")
        self._login_path = login_path

    def received(self, application: ApplicationView) -> None:
        self._send("received", application)

    def approved(self, application: ApplicationView, *, account_created: bool) -> None:
        if account_created and application.reseller_id is not None:
            url = self._accounts.setup_link(application.reseller_id)
        else:
            url = f"{self._base_url}{self._login_path}"
        self._send("approved", application, url=url, account_created=account_created)

    def rejected(self, application: ApplicationView) -> None:
        self._send("rejected", application, reason=application.decision_note)

    def _send(self, name: str, application: ApplicationView, **context: object) -> None:
        queue_templated(
            TEMPLATES.format(name=name),
            to=[application.email],
            subject=SUBJECTS[name],
            context={"first_name": application.first_name, **context},
        )
