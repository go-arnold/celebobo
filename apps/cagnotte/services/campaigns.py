from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from apps.cagnotte.domain import rules
from apps.cagnotte.domain.commands import CampaignInput, PayReward
from apps.cagnotte.domain.errors import (
    CampaignEnded,
    CampaignOverlap,
    CampaignStarted,
    InvalidCampaign,
    PointsDisabled,
    RewardNotDue,
)
from apps.cagnotte.domain.rules import CampaignKind, Payout, RewardStatus, Scope, Terms
from apps.cagnotte.models import Campaign, Reward
from apps.cagnotte.repositories import CampaignRepository, RewardRepository
from apps.cagnotte.services.contracts import Catalog, Orders, PointsLedger, ReturnPolicy
from apps.orders.domain.pricing import CampaignLine, CampaignOffer, spread
from core.domain.actor import Actor


def terms_of(campaign: Campaign) -> Terms:
    return Terms(
        kind=CampaignKind(campaign.kind),
        percent=campaign.percent,
        min_purchase=campaign.min_purchase,
        cap=campaign.cap,
    )


def payout_of(campaign: Campaign) -> Payout:
    # boosted points are points; only a cashback may go by Mobile Money
    if campaign.kind == CampaignKind.CASHBACK.value:
        return Payout(campaign.payout)
    return Payout.POINTS


class CampaignService:
    def __init__(
        self,
        campaigns: CampaignRepository,
        catalog: Catalog,
        points: PointsLedger,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._campaigns = campaigns
        self._catalog = catalog
        self._points = points
        self._clock = clock

    def create(self, actor: Actor, data: CampaignInput) -> Campaign:
        self._check(data, campaign_id=None)
        return self._campaigns.create(
            **self._fields(data),
            created_by_id=actor.user_id,
            category_ids=data.category_ids,
            product_ids=data.product_ids,
        )

    # the conditions are announced: they change only before the operation starts
    def update(self, campaign: Campaign, data: CampaignInput) -> Campaign:
        if campaign.starts_at <= self._clock():
            raise CampaignStarted
        self._check(data, campaign_id=campaign.pk)
        return self._campaigns.update(
            campaign,
            **self._fields(data),
            category_ids=data.category_ids,
            product_ids=data.product_ids,
        )

    def end(self, campaign: Campaign) -> Campaign:
        now = self._clock()
        if campaign.ends_at <= now:
            raise CampaignEnded
        if campaign.starts_at > now:
            raise InvalidCampaign("L'opération n'a pas commencé : supprimez-la.")
        campaign.ends_at = now
        self._campaigns.save(campaign, fields=("ends_at",))
        return campaign

    def delete(self, campaign: Campaign) -> None:
        if campaign.starts_at <= self._clock():
            raise CampaignStarted
        self._campaigns.delete(campaign)

    # the operation running now, for these lines: its discount per line, or the estimate of its
    # cashback or boosted points
    def offer(self, lines: Sequence[CampaignLine]) -> CampaignOffer | None:
        campaign = self._campaigns.running(self._clock())
        if campaign is None:
            return None
        category_ids, product_ids = self._campaigns.scope(campaign)
        scope = Scope(category_ids=category_ids, product_ids=product_ids)
        categories = (
            {} if scope.everything else self._catalog.categories(line.product_id for line in lines)
        )
        eligible = [
            line.total
            if scope.covers(line.product_id, categories.get(line.product_id, frozenset()))
            else rules.ZERO
            for line in lines
        ]
        terms = terms_of(campaign)
        amount = rules.advantage(terms, sum(eligible, rules.ZERO))
        discount = terms.kind is CampaignKind.DISCOUNT
        return CampaignOffer(
            campaign_id=campaign.pk,
            name=campaign.name,
            kind=campaign.kind,
            percent=campaign.percent,
            discounts=tuple(spread(amount, eligible))
            if discount
            else tuple(rules.ZERO for _ in lines),
            advantage=rules.ZERO if discount else amount,
        )

    def _check(self, data: CampaignInput, *, campaign_id: int | None) -> None:
        if not data.name.strip():
            raise InvalidCampaign("Donnez un nom à l'opération.")
        if not rules.MIN_PERCENT <= data.percent <= rules.MAX_PERCENT:
            raise InvalidCampaign("Le pourcentage va de 0,01 à 50 %.")
        if data.ends_at <= data.starts_at:
            raise InvalidCampaign("La fin doit suivre le début.")
        if data.ends_at <= self._clock():
            raise InvalidCampaign("La fin est déjà passée.")
        if data.min_purchase is not None and data.min_purchase < 0:
            raise InvalidCampaign("Le montant minimum ne peut pas être négatif.")
        if data.cap is not None and data.cap <= 0:
            raise InvalidCampaign("Le plafond doit être positif.")
        low, high = rules.VALID_DAYS
        if not low <= data.points_valid_days <= high:
            raise InvalidCampaign("Les points Cagnotte restent valables de 1 à 730 jours.")
        if not self._catalog.known(data.category_ids, data.product_ids):
            raise InvalidCampaign("Une catégorie ou un produit choisi n'existe pas.")
        in_points = data.kind is CampaignKind.BOOSTED_POINTS or (
            data.kind is CampaignKind.CASHBACK and data.payout is Payout.POINTS
        )
        if in_points and not self._points.enabled():
            raise PointsDisabled
        others = self._campaigns.periods(excluding=campaign_id)
        if rules.overlaps(data.starts_at, data.ends_at, others):
            raise CampaignOverlap

    @staticmethod
    def _fields(data: CampaignInput) -> dict[str, object]:
        return {
            "name": data.name.strip()[:120],
            "description": data.description.strip()[:4000],
            "kind": data.kind.value,
            "percent": data.percent,
            "starts_at": data.starts_at,
            "ends_at": data.ends_at,
            "min_purchase": data.min_purchase,
            "cap": data.cap,
            "payout": data.payout.value,
            "points_valid_days": data.points_valid_days,
        }


class RewardService:
    def __init__(
        self,
        rewards: RewardRepository,
        campaigns: CampaignRepository,
        *,
        orders: Orders,
        catalog: Catalog,
        points: PointsLedger,
        returns: ReturnPolicy,
        clock: Callable[[], datetime],
    ) -> None:
        self._rewards = rewards
        self._campaigns = campaigns
        self._orders = orders
        self._catalog = catalog
        self._points = points
        self._returns = returns
        self._clock = clock

    # on delivery: the cashback or boosted points on what the client really paid for the products
    # concerned; pending until the trial is over, like the 1 % points
    def delivered(self, order_id: int, delivered_at: datetime) -> Reward | None:
        if self._rewards.for_order(order_id) is not None:
            return None
        order = self._orders.campaign_order(order_id)
        if order is None or order.campaign_id is None:
            return None
        campaign = self._campaigns.get(order.campaign_id)
        if campaign is None or campaign.kind == CampaignKind.DISCOUNT.value:
            return None
        amount = self._amount(campaign, order_id)
        if amount <= 0:
            return None
        payout = payout_of(campaign)
        available_at = delivered_at + timedelta(days=self._returns.return_days())
        reward = self._rewards.create(
            campaign=campaign,
            order_id=order_id,
            client_id=order.client_id,
            kind=campaign.kind,
            payout=payout.value,
            amount=amount,
            kept=amount,
            status=(
                RewardStatus.CREDITED if payout is Payout.POINTS else RewardStatus.TO_PAY
            ).value,
            available_at=available_at,
        )
        if payout is Payout.POINTS:
            self._points.credit(
                order.client_id,
                order_id,
                amount,
                available_at=available_at,
                expires_at=available_at + timedelta(days=campaign.points_valid_days),
            )
        return reward

    # units came back: the advantage is computed again on what is left (below the minimum
    # purchase, nothing); the difference is taken back
    def line_returned(self, order_id: int) -> None:
        reward = self._rewards.for_order(order_id, for_update=True)
        if reward is None or reward.status == RewardStatus.CANCELLED.value:
            return
        self._take_back(reward, reward.kept - self._amount(reward.campaign, order_id))

    # cancelled or returned whole: the advantage is cancelled
    def undone(self, order_id: int) -> None:
        reward = self._rewards.for_order(order_id, for_update=True)
        if reward is None or reward.status == RewardStatus.CANCELLED.value:
            return
        self._take_back(reward, reward.kept)

    def pay(self, actor: Actor, reward: Reward, command: PayReward) -> Reward:
        now = self._clock()
        due = (
            reward.status == RewardStatus.TO_PAY.value
            and reward.kept > 0
            and reward.available_at <= now
        )
        if not due:
            raise RewardNotDue
        reward.status = RewardStatus.PAID.value
        reward.paid_at = now
        reward.paid_by_id = actor.user_id
        reward.reference = command.reference.strip()[:80]
        self._rewards.save(reward, fields=("status", "paid_at", "paid_by", "reference"))
        return reward

    def _take_back(self, reward: Reward, amount: Decimal) -> None:
        if amount <= 0:
            return
        reward.kept -= amount
        fields = ["kept"]
        if reward.payout == Payout.POINTS.value:
            self._points.reverse(reward.order_id, amount)
        elif reward.status == RewardStatus.PAID.value:
            # already sent by Mobile Money: staff deduct it from the refund
            reward.owed_back += amount
            fields.append("owed_back")
        if reward.kept <= 0 and reward.status == RewardStatus.TO_PAY.value:
            reward.status = RewardStatus.CANCELLED.value
            fields.append("status")
        self._rewards.save(reward, fields=fields)

    def _amount(self, campaign: Campaign, order_id: int) -> Decimal:
        order = self._orders.campaign_order(order_id)
        if order is None:
            return rules.ZERO
        category_ids, product_ids = self._campaigns.scope(campaign)
        scope = Scope(category_ids=category_ids, product_ids=product_ids)
        ids = [line.product_id for line in order.lines if line.product_id is not None]
        categories = {} if scope.everything else self._catalog.categories(ids)
        eligible = sum(
            (
                line.paid
                for line in order.lines
                if line.product_id is not None
                and scope.covers(line.product_id, categories.get(line.product_id, frozenset()))
            ),
            rules.ZERO,
        )
        return rules.advantage(terms_of(campaign), eligible)
