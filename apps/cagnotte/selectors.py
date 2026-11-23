from collections.abc import Callable
from datetime import datetime

from django.db.models import QuerySet

from apps.cagnotte.domain.errors import CampaignNotFound
from apps.cagnotte.domain.read_models import CampaignView, NamedRef, RewardView
from apps.cagnotte.domain.rules import CampaignKind, Payout, RewardStatus
from apps.cagnotte.models import Campaign, Reward


def state_of(campaign: Campaign, now: datetime) -> str:
    if campaign.starts_at > now:
        return "upcoming"
    return "running" if campaign.ends_at > now else "ended"


def campaign_view(campaign: Campaign, now: datetime) -> CampaignView:
    kind = CampaignKind(campaign.kind)
    return CampaignView(
        id=campaign.pk,
        name=campaign.name,
        description=campaign.description,
        kind=kind,
        percent=campaign.percent,
        starts_at=campaign.starts_at,
        ends_at=campaign.ends_at,
        min_purchase=campaign.min_purchase,
        cap=campaign.cap,
        payout=Payout(campaign.payout) if kind is CampaignKind.CASHBACK else None,
        points_valid_days=None if kind is CampaignKind.DISCOUNT else campaign.points_valid_days,
        categories=tuple(NamedRef(id=c.pk, name=c.name) for c in campaign.categories.all()),
        products=tuple(NamedRef(id=p.pk, name=p.name) for p in campaign.products.all()),
        state=state_of(campaign, now),
        created_at=campaign.created_at,
    )


def reward_view(reward: Reward) -> RewardView:
    client = reward.client
    return RewardView(
        id=reward.pk,
        campaign_id=reward.campaign_id,
        campaign_name=reward.campaign.name,
        kind=CampaignKind(reward.kind),
        payout=Payout(reward.payout),
        order_id=reward.order_id,
        order_number=reward.order.number,
        client_id=reward.client_id,
        client_name=client.get_full_name() or client.email,
        phone=reward.order.phone,
        amount=reward.amount,
        kept=reward.kept,
        owed_back=reward.owed_back,
        status=RewardStatus(reward.status),
        available_at=reward.available_at,
        paid_at=reward.paid_at,
        reference=reward.reference,
        created_at=reward.created_at,
    )


class CampaignSelector:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def _rows(self) -> QuerySet[Campaign]:
        return Campaign.objects.prefetch_related("categories", "products")

    def all(self) -> list[CampaignView]:
        now = self._clock()
        return [campaign_view(row, now) for row in self._rows()]

    def one(self, campaign_id: int) -> CampaignView:
        row = self._rows().filter(pk=campaign_id).first()
        if row is None:
            raise CampaignNotFound
        return campaign_view(row, self._clock())

    def current(self) -> CampaignView | None:
        now = self._clock()
        row = self._rows().filter(starts_at__lte=now, ends_at__gt=now).first()
        return campaign_view(row, now) if row else None


class RewardSelector:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def _rows(self) -> QuerySet[Reward]:
        return Reward.objects.select_related("campaign", "order", "client")

    # staff: ``due`` lists the Mobile Money cashbacks to send now
    def page(
        self, *, status: RewardStatus | None, due: bool, offset: int, limit: int
    ) -> tuple[list[RewardView], int]:
        rows = self._rows()
        if due:
            rows = rows.filter(
                status=RewardStatus.TO_PAY.value, kept__gt=0, available_at__lte=self._clock()
            )
        elif status is not None:
            rows = rows.filter(status=status.value)
        return [reward_view(row) for row in rows[offset : offset + limit]], rows.count()

    def mine(self, client_id: int, *, limit: int = 50) -> list[RewardView]:
        rows = self._rows().filter(client_id=client_id).order_by("-created_at", "-pk")
        return [reward_view(row) for row in rows[:limit]]

    def one(self, reward_id: int) -> RewardView:
        return reward_view(self._rows().get(pk=reward_id))
