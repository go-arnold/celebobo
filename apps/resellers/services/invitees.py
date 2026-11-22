from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from apps.accounts.domain.read_models import Invitee
from apps.loyalty.domain.points import add_months
from apps.resellers.domain.read_models import (
    InviteesPage,
    InviteeView,
    OwnInviteesPage,
    OwnInviteeView,
)
from apps.resellers.services.contracts import InviteeOrders, ReferralTerms, ResellerDirectory

UNNAMED = "Client sans nom"


class InviteeService:
    def __init__(
        self,
        directory: ResellerDirectory,
        orders: InviteeOrders,
        terms: ReferralTerms,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._directory = directory
        self._orders = orders
        self._terms = terms
        self._clock = clock

    # the reseller's own list: no e-mail and no purchase figures (privacy policy §4)
    def own_page(self, reseller_id: int, *, offset: int, limit: int) -> tuple[OwnInviteesPage, int]:
        reseller = self._directory.one(reseller_id)
        invitees, total = self._directory.invitees(reseller_id, offset=offset, limit=limit)
        months, now = self._terms.months(), self._clock()
        page = OwnInviteesPage(
            code=reseller.referral_code,
            invited_count=total,
            invitees=[_own_view(invitee, months, now) for invitee in invitees],
        )
        return page, total

    # staff only (resellers directory): with each invitee's e-mail and purchase totals

    def page(self, reseller_id: int, *, offset: int, limit: int) -> tuple[InviteesPage, int]:
        reseller = self._directory.one(reseller_id)
        invitees, total = self._directory.invitees(reseller_id, offset=offset, limit=limit)
        everyone = self._orders.totals(self._directory.invitee_ids(reseller_id))
        views = [
            InviteeView(
                id=invitee.id,
                name=invitee.name,
                email=invitee.email,
                joined_at=invitee.joined_at,
                orders_count=everyone[invitee.id].count if invitee.id in everyone else 0,
                orders_total=everyone[invitee.id].total if invitee.id in everyone else Decimal(0),
            )
            for invitee in invitees
        ]
        page = InviteesPage(
            code=reseller.referral_code,
            invited_count=total,
            orders_total=sum((totals.total for totals in everyone.values()), Decimal("0.00")),
            invitees=views,
        )
        return page, total


def _own_view(invitee: Invitee, months: int, now: datetime) -> OwnInviteeView:
    ends_at = add_months(invitee.invited_at, months) if invitee.invited_at else None
    return OwnInviteeView(
        id=invitee.id,
        name=invitee.full_name or UNNAMED,
        joined_at=invitee.joined_at,
        referral_ends_at=ends_at,
        referral_active=ends_at is not None and now < ends_at,
    )
