import re
from collections.abc import Callable
from datetime import datetime, timedelta

from apps.loyalty.domain.errors import (
    MembershipRequestNotFound,
    ProgrammeClosed,
    RequestAlreadyHandled,
    RequestAlreadyPending,
    TrialUnavailable,
)
from apps.loyalty.domain.membership import (
    PAID_MONTHS,
    MembershipStatus,
    MemberView,
    Plan,
    RequestMembership,
    RequestStatus,
    add_months,
    membership_status,
)
from apps.loyalty.models import LoyaltySettings, Membership, MembershipRequest
from apps.loyalty.repositories import (
    LoyaltySettingsRepository,
    MembershipRepository,
    MembershipRequestRepository,
)
from apps.loyalty.selectors import to_request_view
from apps.loyalty.services.contracts import People

_NOT_DIGITS = re.compile(r"\D")


class MembershipService:
    def __init__(
        self,
        memberships: MembershipRepository,
        requests: MembershipRequestRepository,
        settings: LoyaltySettingsRepository,
        people: People,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._memberships = memberships
        self._requests = requests
        self._settings = settings
        self._people = people
        self._clock = clock

    def view(self, user_id: int) -> MemberView:
        membership = self._memberships.for_user(user_id)
        pending = self._requests.pending_for(user_id)
        settings = self._settings.current()
        status = membership_status(
            membership.plan if membership else "",
            membership.ends_at if membership else None,
            self._clock(),
        )
        return MemberView(
            status=status,
            plan=Plan(membership.plan) if membership else None,
            ends_at=membership.ends_at if membership else None,
            trial_available=settings.membership_enabled
            and settings.membership_trial_days > 0
            and (membership is None or membership.trial_started_at is None),
            pending_request=to_request_view(pending) if pending else None,
        )

    def start_trial(self, user_id: int) -> Membership:
        settings = self._open()
        person = self._people.requester(user_id)
        if not person.email_verified:
            raise TrialUnavailable(
                "email_unverified", "Confirmez votre adresse e-mail pour commencer l'essai."
            )
        phone = _NOT_DIGITS.sub("", person.phone or "")
        if not phone:
            raise TrialUnavailable(
                "phone_missing", "Ajoutez votre numéro de téléphone pour commencer l'essai."
            )
        now = self._clock()
        membership = self._memberships.for_user(user_id, for_update=True)
        if settings.membership_trial_days == 0 or (membership and membership.trial_started_at):
            raise TrialUnavailable("trial_used", "Vous avez déjà profité de l'essai gratuit.")
        if membership and membership.ends_at > now:
            raise TrialUnavailable("already_member", "Votre abonnement est déjà actif.")
        if self._memberships.trial_phone_used(phone, user_id=user_id):
            raise TrialUnavailable(
                "phone_used", "Ce numéro de téléphone a déjà servi pour un essai gratuit."
            )
        values = {
            "plan": Plan.TRIAL.value,
            "ends_at": now + timedelta(days=settings.membership_trial_days),
            "trial_started_at": now,
            "trial_phone": phone,
            "reminded_for": None,
        }
        return self._extend(user_id, membership, values)

    def request(self, user_id: int, command: RequestMembership) -> MembershipRequest:
        settings = self._open()
        if self._requests.pending_for(user_id) is not None:
            raise RequestAlreadyPending
        price = (
            settings.membership_yearly_price
            if command.plan is Plan.YEARLY
            else settings.membership_monthly_price
        )
        return self._requests.create(
            user_id=user_id,
            plan=command.plan.value,
            price=price,
            payment_method=command.payment_method,
        )

    def cancel(self, user_id: int, request_id: int) -> None:
        request = self._pending(request_id)
        if request.user_id != user_id:
            raise MembershipRequestNotFound
        self._close(request, RequestStatus.CANCELLED, handled_by=None)

    # a paid period starts when the current one ends, so a member never loses days
    def confirm(self, request_id: int, staff_id: int | None) -> Membership:
        request = self._pending(request_id)
        now = self._clock()
        membership = self._memberships.for_user(request.user_id, for_update=True)
        start = max(now, membership.ends_at) if membership else now
        values = {
            "plan": request.plan,
            "ends_at": add_months(start, PAID_MONTHS[Plan(request.plan)]),
            "reminded_for": None,
        }
        self._close(request, RequestStatus.CONFIRMED, handled_by=staff_id)
        return self._extend(request.user_id, membership, values)

    def reject(self, request_id: int, staff_id: int | None, note: str) -> MembershipRequest:
        request = self._pending(request_id)
        request.note = note.strip()
        self._close(request, RequestStatus.REJECTED, handled_by=staff_id, fields=("note",))
        return request

    def is_member(self, user_id: int) -> bool:
        return self._memberships.active(user_id, self._clock())

    def status(self, membership: Membership) -> MembershipStatus:
        return membership_status(membership.plan, membership.ends_at, self._clock())

    def ending(self) -> list[Membership]:
        now = self._clock()
        days = self._settings.current().membership_reminder_days
        if days == 0:
            return []
        due = self._memberships.ending(now, now + timedelta(days=days))
        for membership in due:
            membership.reminded_for = membership.ends_at
            self._memberships.save(membership, fields=("reminded_for",))
        return due

    def _open(self) -> LoyaltySettings:
        settings = self._settings.current()
        if not settings.membership_enabled:
            raise ProgrammeClosed
        return settings

    def _pending(self, request_id: int) -> MembershipRequest:
        request = self._requests.get(request_id, for_update=True)
        if request is None:
            raise MembershipRequestNotFound
        if request.status != RequestStatus.PENDING.value:
            raise RequestAlreadyHandled
        return request

    def _close(
        self,
        request: MembershipRequest,
        status: RequestStatus,
        *,
        handled_by: int | None,
        fields: tuple[str, ...] = (),
    ) -> None:
        request.status = status.value
        request.handled_by_id = handled_by
        request.handled_at = self._clock()
        self._requests.save(request, fields=("status", "handled_by", "handled_at", *fields))

    def _extend(
        self, user_id: int, membership: Membership | None, values: dict[str, object]
    ) -> Membership:
        if membership is None:
            return self._memberships.create(user_id=user_id, **values)
        for name, value in values.items():
            setattr(membership, name, value)
        self._memberships.save(membership, fields=tuple(values))
        return membership
