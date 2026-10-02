from decimal import Decimal

from apps.resellers.domain.read_models import InviteesPage, InviteeView
from apps.resellers.services.contracts import InviteeOrders, ResellerDirectory


class InviteeService:
    def __init__(self, directory: ResellerDirectory, orders: InviteeOrders) -> None:
        self._directory = directory
        self._orders = orders

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
