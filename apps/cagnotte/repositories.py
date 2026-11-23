from collections.abc import Iterable
from datetime import datetime
from typing import Any

from apps.cagnotte.models import Campaign, Reward


class CampaignRepository:
    def get(self, campaign_id: int, *, for_update: bool = False) -> Campaign | None:
        rows = Campaign.objects.select_for_update() if for_update else Campaign.objects
        return rows.filter(pk=campaign_id).first()

    def create(
        self, *, category_ids: Iterable[int], product_ids: Iterable[int], **fields: Any
    ) -> Campaign:
        campaign = Campaign.objects.create(**fields)
        campaign.categories.set(list(category_ids))
        campaign.products.set(list(product_ids))
        return campaign

    def update(
        self,
        campaign: Campaign,
        *,
        category_ids: Iterable[int],
        product_ids: Iterable[int],
        **fields: Any,
    ) -> Campaign:
        for name, value in fields.items():
            setattr(campaign, name, value)
        campaign.save()
        campaign.categories.set(list(category_ids))
        campaign.products.set(list(product_ids))
        return campaign

    def save(self, campaign: Campaign, *, fields: Iterable[str]) -> None:
        campaign.save(update_fields=[*fields, "updated_at"])

    def delete(self, campaign: Campaign) -> None:
        campaign.delete()

    # the periods of the other operations, to keep one at a time
    def periods(self, *, excluding: int | None = None) -> list[tuple[datetime, datetime]]:
        rows = Campaign.objects.all()
        if excluding is not None:
            rows = rows.exclude(pk=excluding)
        return list(rows.values_list("starts_at", "ends_at"))

    def running(self, now: datetime) -> Campaign | None:
        return (
            Campaign.objects.filter(starts_at__lte=now, ends_at__gt=now)
            .prefetch_related("categories", "products")
            .first()
        )

    def scope(self, campaign: Campaign) -> tuple[frozenset[int], frozenset[int]]:
        return (
            frozenset(campaign.categories.values_list("pk", flat=True)),
            frozenset(campaign.products.values_list("pk", flat=True)),
        )


class RewardRepository:
    def for_order(self, order_id: int, *, for_update: bool = False) -> Reward | None:
        rows = Reward.objects.select_for_update() if for_update else Reward.objects
        return rows.select_related("campaign").filter(order_id=order_id).first()

    def get(self, reward_id: int, *, for_update: bool = False) -> Reward | None:
        rows = Reward.objects.select_for_update() if for_update else Reward.objects
        return rows.filter(pk=reward_id).first()

    def create(self, **fields: Any) -> Reward:
        return Reward.objects.create(**fields)

    def save(self, reward: Reward, *, fields: Iterable[str]) -> None:
        reward.save(update_fields=[*fields])
