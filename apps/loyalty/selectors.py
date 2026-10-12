from datetime import datetime
from typing import Any

from apps.loyalty.domain.membership import (
    AdminMemberRow,
    AdminRequestRow,
    MemberRef,
    MembershipStatus,
    Plan,
    RequestStatus,
    RequestView,
    membership_status,
)
from apps.loyalty.domain.settings import AppLinks, CashbackTerms, MembershipTerms, Programmes
from apps.loyalty.models import LoyaltySettings, Membership, MembershipRequest


def to_programmes(settings: LoyaltySettings) -> Programmes:
    return Programmes(
        membership=MembershipTerms(
            enabled=settings.membership_enabled,
            monthly_price=settings.membership_monthly_price,
            yearly_price=settings.membership_yearly_price,
            trial_days=settings.membership_trial_days,
            reminder_days=settings.membership_reminder_days,
        ),
        cashback=CashbackTerms(
            enabled=settings.cashback_enabled,
            percent=settings.cashback_percent,
            max_share=settings.cashback_max_share,
            min_balance=settings.cashback_min_balance,
            validity_months=settings.cashback_validity_months,
        ),
        app_links=AppLinks(app_store=settings.app_store_url, play_store=settings.play_store_url),
    )


class MembershipSelector:
    def requests(
        self, status: RequestStatus | None, *, offset: int, limit: int
    ) -> tuple[list[AdminRequestRow], int]:
        rows = MembershipRequest.objects.select_related("user")
        if status is not None:
            rows = rows.filter(status=status.value)
        page = rows[offset : offset + limit]
        return [
            AdminRequestRow(request=to_request_view(row), member=_member(row.user)) for row in page
        ], rows.count()

    def members(
        self, status: MembershipStatus | None, *, now: datetime, offset: int, limit: int
    ) -> tuple[list[AdminMemberRow], int]:
        rows = Membership.objects.select_related("user").order_by("ends_at", "pk")
        if status is MembershipStatus.EXPIRED:
            rows = rows.filter(ends_at__lte=now)
        elif status is MembershipStatus.TRIAL:
            rows = rows.filter(ends_at__gt=now, plan=Plan.TRIAL.value)
        elif status is MembershipStatus.ACTIVE:
            rows = rows.filter(ends_at__gt=now).exclude(plan=Plan.TRIAL.value)
        page = rows[offset : offset + limit]
        return [
            AdminMemberRow(
                member=_member(row.user),
                status=membership_status(row.plan, row.ends_at, now),
                plan=Plan(row.plan),
                ends_at=row.ends_at,
            )
            for row in page
        ], rows.count()


def to_request_view(request: MembershipRequest) -> RequestView:
    return RequestView(
        id=request.pk,
        plan=Plan(request.plan),
        price=request.price,
        payment_method=request.payment_method,
        status=RequestStatus(request.status),
        note=request.note,
        created_at=request.created_at,
        handled_at=request.handled_at,
    )


def _member(user: Any) -> MemberRef:
    return MemberRef(
        id=user.pk,
        name=user.get_full_name() or user.email,
        email=user.email,
        phone=user.phone_number or "",
    )
