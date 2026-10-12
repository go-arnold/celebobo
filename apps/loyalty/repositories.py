from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db.models import F

from apps.loyalty.domain.membership import RequestStatus
from apps.loyalty.models import SETTINGS_ID, LoyaltySettings, Membership, MembershipRequest


class LoyaltySettingsRepository:
    def current(self, *, for_update: bool = False) -> LoyaltySettings:
        settings = (
            LoyaltySettings.objects.select_for_update() if for_update else LoyaltySettings.objects
        )
        current, _ = settings.get_or_create(pk=SETTINGS_ID)
        return current

    def save(self, settings: LoyaltySettings, *, fields: Iterable[str]) -> None:
        settings.save(update_fields=[*fields, "updated_at"])


class MembershipRepository:
    def for_user(self, user_id: int, *, for_update: bool = False) -> Membership | None:
        rows = Membership.objects.select_for_update() if for_update else Membership.objects
        return rows.filter(user_id=user_id).first()

    def create(self, **fields: Any) -> Membership:
        membership: Membership = Membership.objects.create(**fields)
        return membership

    def save(self, membership: Membership, *, fields: Iterable[str]) -> None:
        membership.save(update_fields=[*fields, "updated_at"])

    def trial_phone_used(self, phone: str, *, user_id: int) -> bool:
        return Membership.objects.filter(trial_phone=phone).exclude(user_id=user_id).exists()

    def active(self, user_id: int, now: datetime) -> bool:
        return Membership.objects.filter(user_id=user_id, ends_at__gt=now).exists()

    def ending(self, now: datetime, until: datetime) -> list[Membership]:
        return list(
            Membership.objects.select_for_update()
            .filter(ends_at__gt=now, ends_at__lte=until)
            .exclude(reminded_for=F("ends_at"))
        )


class MembershipRequestRepository:
    def create(self, **fields: Any) -> MembershipRequest:
        request: MembershipRequest = MembershipRequest.objects.create(**fields)
        return request

    def get(self, request_id: int, *, for_update: bool = False) -> MembershipRequest | None:
        rows = (
            MembershipRequest.objects.select_for_update()
            if for_update
            else MembershipRequest.objects
        )
        return rows.filter(pk=request_id).first()

    def pending_for(self, user_id: int) -> MembershipRequest | None:
        return MembershipRequest.objects.filter(
            user_id=user_id, status=RequestStatus.PENDING.value
        ).first()

    def save(self, request: MembershipRequest, *, fields: Iterable[str]) -> None:
        request.save(update_fields=list(fields))
