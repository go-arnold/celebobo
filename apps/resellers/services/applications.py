from collections.abc import Callable
from datetime import datetime

from django.db import IntegrityError, transaction

from apps.accounts.domain.commands import OnboardReseller
from apps.accounts.domain.normalization import clean_text, normalize_email, normalize_phone
from apps.accounts.domain.read_models import OnboardedReseller
from apps.resellers.domain.commands import ApproveApplication, RejectApplication, SubmitApplication
from apps.resellers.domain.enums import ApplicationStatus
from apps.resellers.domain.errors import AlreadyReseller, ApplicationPending, ApplicationReviewed
from apps.resellers.models import ResellerApplication
from apps.resellers.repositories import ApplicationRepository
from apps.resellers.services.contracts import ResellerAccounts, ResellerDirectory
from core.domain.actor import Actor


class ApplicationService:
    def __init__(
        self,
        applications: ApplicationRepository,
        accounts: ResellerAccounts,
        directory: ResellerDirectory,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._applications = applications
        self._accounts = accounts
        self._directory = directory
        self._clock = clock

    def submit(self, actor: Actor, command: SubmitApplication) -> ResellerApplication:
        email = normalize_email(command.email)
        if self._directory.is_reseller(email):
            raise AlreadyReseller
        if self._applications.pending_for(email):
            raise ApplicationPending
        try:
            with transaction.atomic():
                return self._applications.create(
                    first_name=clean_text(command.first_name),
                    last_name=clean_text(command.last_name),
                    email=email,
                    phone_number=normalize_phone(command.phone_number) or "",
                    city=clean_text(command.city),
                    message=command.message.strip(),
                    applicant_id=actor.user_id,
                )
        except IntegrityError as error:
            raise ApplicationPending from error

    def approve(
        self, actor: Actor, application: ResellerApplication, command: ApproveApplication
    ) -> OnboardedReseller:
        self._ensure_pending(application)
        onboarded = self._accounts.onboard(
            actor,
            OnboardReseller(
                email=application.email,
                first_name=application.first_name,
                last_name=application.last_name,
                phone_number=application.phone_number or None,
                commission_rate=command.commission_rate,
                manager_id=command.manager_id,
            ),
        )
        application.reseller_id = onboarded.user_id
        self._close(actor, application, ApplicationStatus.APPROVED, extra=("reseller",))
        return onboarded

    def reject(
        self, actor: Actor, application: ResellerApplication, command: RejectApplication
    ) -> None:
        self._ensure_pending(application)
        application.decision_note = command.reason.strip()
        self._close(actor, application, ApplicationStatus.REJECTED, extra=("decision_note",))

    def _close(
        self,
        actor: Actor,
        application: ResellerApplication,
        status: ApplicationStatus,
        *,
        extra: tuple[str, ...],
    ) -> None:
        application.status = status.value
        application.reviewed_by_id = actor.user_id
        application.reviewed_at = self._clock()
        self._applications.save(
            application, fields=("status", "reviewed_by", "reviewed_at", *extra)
        )

    @staticmethod
    def _ensure_pending(application: ResellerApplication) -> None:
        if application.application_status is not ApplicationStatus.PENDING:
            raise ApplicationReviewed
