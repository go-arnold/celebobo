from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from django.db import transaction

from apps.loyalty.domain.cashback import Balance
from apps.loyalty.domain.events import (
    LoyaltySettingsChanged,
    MembershipEnding,
    MembershipRequested,
    MembershipRequestRejected,
    MembershipStarted,
)
from apps.loyalty.domain.membership import (
    AdminMemberRow,
    AdminRequestRow,
    MembershipStatus,
    MemberView,
    RequestMembership,
    RequestStatus,
)
from apps.loyalty.domain.settings import LoyaltySettingsChanges, Programmes
from apps.loyalty.models import Membership
from apps.loyalty.selectors import MembershipSelector, to_programmes
from apps.loyalty.services.cashback import CashbackService
from apps.loyalty.services.contracts import People
from apps.loyalty.services.membership import MembershipService
from apps.loyalty.services.settings import LoyaltySettingsService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class LoyaltyFacade:
    def __init__(self, *, settings: LoyaltySettingsService, publisher: EventPublisher) -> None:
        self._settings = settings
        self._publisher = publisher

    def programmes(self) -> Programmes:
        return to_programmes(self._settings.current())

    def update(self, actor: Actor, changes: LoyaltySettingsChanges) -> Programmes:
        with transaction.atomic():
            if self._settings.update(changes):
                self._publisher.publish(LoyaltySettingsChanged(actor_id=actor.user_id))
        return self.programmes()


@logged_facade
class MembershipFacade:
    def __init__(
        self,
        *,
        memberships: MembershipService,
        selector: MembershipSelector,
        people: People,
        publisher: EventPublisher,
        clock: Callable[[], datetime],
    ) -> None:
        self._memberships = memberships
        self._selector = selector
        self._people = people
        self._publisher = publisher
        self._clock = clock

    def mine(self, actor: Actor) -> MemberView:
        return self._memberships.view(_user_id(actor))

    def start_trial(self, actor: Actor) -> MemberView:
        user_id = _user_id(actor)
        with transaction.atomic():
            membership = self._memberships.start_trial(user_id)
            self._started(membership, actor)
        return self.mine(actor)

    def request(self, actor: Actor, command: RequestMembership) -> MemberView:
        user_id = _user_id(actor)
        with transaction.atomic():
            request = self._memberships.request(user_id, command)
            self._publisher.publish(
                MembershipRequested(
                    request_id=request.pk,
                    user_id=user_id,
                    client_name=self._people.requester(user_id).name,
                    plan=request.plan,
                    actor_id=user_id,
                )
            )
        return self.mine(actor)

    def cancel(self, actor: Actor, request_id: int) -> MemberView:
        with transaction.atomic():
            self._memberships.cancel(_user_id(actor), request_id)
        return self.mine(actor)

    def requests(
        self, status: RequestStatus | None, *, offset: int, limit: int
    ) -> tuple[list[AdminRequestRow], int]:
        return self._selector.requests(status, offset=offset, limit=limit)

    def members(
        self, status: MembershipStatus | None, *, offset: int, limit: int
    ) -> tuple[list[AdminMemberRow], int]:
        return self._selector.members(status, now=self._clock(), offset=offset, limit=limit)

    def confirm(self, actor: Actor, request_id: int) -> None:
        with transaction.atomic():
            membership = self._memberships.confirm(request_id, actor.user_id)
            self._started(membership, actor)

    def reject(self, actor: Actor, request_id: int, note: str) -> None:
        with transaction.atomic():
            request = self._memberships.reject(request_id, actor.user_id, note)
            self._publisher.publish(
                MembershipRequestRejected(
                    user_id=request.user_id,
                    request_id=request.pk,
                    note=request.note,
                    actor_id=actor.user_id,
                )
            )

    def remind(self) -> int:
        with transaction.atomic():
            due = self._memberships.ending()
            for membership in due:
                self._publisher.publish(
                    MembershipEnding(user_id=membership.user_id, ends_at=membership.ends_at)
                )
        return len(due)

    def _started(self, membership: Membership, actor: Actor) -> None:
        self._publisher.publish(
            MembershipStarted(
                user_id=membership.user_id,
                plan=membership.plan,
                ends_at=membership.ends_at,
                actor_id=actor.user_id,
            )
        )


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id


@logged_facade
class CashbackFacade:
    def __init__(self, *, cashback: CashbackService) -> None:
        self._cashback = cashback

    def mine(self, actor: Actor) -> Balance:
        return self._cashback.balance(_user_id(actor))

    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return self._cashback.usable(user_id, base, lock=lock)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        self._cashback.spend(user_id, order_id, amount)

    def earned(self, order_id: int) -> Decimal | None:
        return self._cashback.earned(order_id)

    def delivered(self, order_id: int, delivered_at: datetime) -> None:
        with transaction.atomic():
            self._cashback.earn(order_id, delivered_at)

    def undone(self, order_id: int) -> None:
        with transaction.atomic():
            self._cashback.undo(order_id)

    def expire(self) -> int:
        with transaction.atomic():
            return self._cashback.expire()
