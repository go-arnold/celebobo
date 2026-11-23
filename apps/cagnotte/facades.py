from datetime import datetime

from django.db import transaction

from apps.cagnotte.domain.commands import CampaignInput, PayReward
from apps.cagnotte.domain.errors import CampaignNotFound, RewardNotFound
from apps.cagnotte.domain.events import CampaignChanged, CashbackPaid
from apps.cagnotte.domain.read_models import CampaignView, RewardView
from apps.cagnotte.domain.rules import RewardStatus
from apps.cagnotte.models import Campaign
from apps.cagnotte.repositories import CampaignRepository, RewardRepository
from apps.cagnotte.selectors import CampaignSelector, RewardSelector
from apps.cagnotte.services.campaigns import CampaignService, RewardService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class CagnotteFacade:
    def __init__(
        self,
        *,
        campaigns: CampaignService,
        rewards: RewardService,
        campaign_repository: CampaignRepository,
        reward_repository: RewardRepository,
        campaign_selector: CampaignSelector,
        reward_selector: RewardSelector,
        publisher: EventPublisher,
    ) -> None:
        self._campaigns = campaigns
        self._rewards = rewards
        self._campaign_repository = campaign_repository
        self._reward_repository = reward_repository
        self._campaign_selector = campaign_selector
        self._reward_selector = reward_selector
        self._publisher = publisher

    # --- the shop

    def current(self) -> CampaignView | None:
        return self._campaign_selector.current()

    def mine(self, actor: Actor) -> list[RewardView]:
        if actor.user_id is None:
            raise Unauthenticated
        return self._reward_selector.mine(actor.user_id)

    # --- staff: operations

    def campaigns(self) -> list[CampaignView]:
        return self._campaign_selector.all()

    def campaign(self, campaign_id: int) -> CampaignView:
        return self._campaign_selector.one(campaign_id)

    def create(self, actor: Actor, data: CampaignInput) -> CampaignView:
        with transaction.atomic():
            campaign = self._campaigns.create(actor, data)
            self._changed(campaign.pk, "created", actor)
        return self._campaign_selector.one(campaign.pk)

    def update(self, actor: Actor, campaign_id: int, data: CampaignInput) -> CampaignView:
        with transaction.atomic():
            self._campaigns.update(self._locked(campaign_id), data)
            self._changed(campaign_id, "updated", actor)
        return self._campaign_selector.one(campaign_id)

    def end(self, actor: Actor, campaign_id: int) -> CampaignView:
        with transaction.atomic():
            self._campaigns.end(self._locked(campaign_id))
            self._changed(campaign_id, "ended", actor)
        return self._campaign_selector.one(campaign_id)

    def delete(self, actor: Actor, campaign_id: int) -> None:
        with transaction.atomic():
            self._campaigns.delete(self._locked(campaign_id))
            self._changed(campaign_id, "deleted", actor)

    # --- staff: Mobile Money cashbacks

    def rewards(
        self, *, status: RewardStatus | None, due: bool, offset: int, limit: int
    ) -> tuple[list[RewardView], int]:
        return self._reward_selector.page(status=status, due=due, offset=offset, limit=limit)

    def pay(self, actor: Actor, reward_id: int, command: PayReward) -> RewardView:
        with transaction.atomic():
            reward = self._reward_repository.get(reward_id, for_update=True)
            if reward is None:
                raise RewardNotFound
            self._rewards.pay(actor, reward, command)
            view = self._reward_selector.one(reward_id)
            self._publisher.publish(
                CashbackPaid(
                    reward_id=reward_id,
                    client_id=view.client_id,
                    order_number=view.order_number,
                    amount=view.kept,
                    reference=view.reference,
                    actor_id=actor.user_id,
                )
            )
        return view

    # --- order events

    def delivered(self, order_id: int, delivered_at: datetime) -> None:
        with transaction.atomic():
            self._rewards.delivered(order_id, delivered_at)

    def line_returned(self, order_id: int) -> None:
        with transaction.atomic():
            self._rewards.line_returned(order_id)

    def undone(self, order_id: int) -> None:
        with transaction.atomic():
            self._rewards.undone(order_id)

    def _locked(self, campaign_id: int) -> Campaign:
        campaign = self._campaign_repository.get(campaign_id, for_update=True)
        if campaign is None:
            raise CampaignNotFound
        return campaign

    def _changed(self, campaign_id: int, change: str, actor: Actor) -> None:
        self._publisher.publish(
            CampaignChanged(campaign_id=campaign_id, change=change, actor_id=actor.user_id)
        )
