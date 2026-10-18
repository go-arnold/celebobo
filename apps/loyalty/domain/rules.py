from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Trigger(StrEnum):
    USER_REGISTERED = "user_registered"
    USER_LOGIN_DAILY = "user_login_daily"
    NEWSLETTER_SUBSCRIBED = "newsletter_subscribed"
    PROFILE_COMPLETED = "profile_completed"
    FIRST_PURCHASE = "first_purchase"
    PURCHASE_MADE = "purchase_made"
    ORDER_VALUE_MILESTONE = "order_value_milestone"
    PRODUCT_PURCHASED = "product_purchased"
    CATEGORY_PURCHASED = "category_purchased"
    REVIEW_CREATED = "review_created"
    FRIEND_REFERRED = "friend_referred"
    SOCIAL_SHARED = "social_shared"
    BIRTHDAY_REACHED = "birthday_reached"
    WINBACK_INACTIVITY = "winback_inactivity"


# triggers grouped by category for the admin dashboard
TRIGGER_CATEGORIES: dict[str, list[Trigger]] = {
    "account_engagement": [
        Trigger.USER_REGISTERED,
        Trigger.USER_LOGIN_DAILY,
        Trigger.NEWSLETTER_SUBSCRIBED,
        Trigger.PROFILE_COMPLETED,
    ],
    "purchase": [
        Trigger.FIRST_PURCHASE,
        Trigger.PURCHASE_MADE,
        Trigger.ORDER_VALUE_MILESTONE,
        Trigger.PRODUCT_PURCHASED,
        Trigger.CATEGORY_PURCHASED,
    ],
    "social_advocacy": [
        Trigger.REVIEW_CREATED,
        Trigger.FRIEND_REFERRED,
        Trigger.SOCIAL_SHARED,
    ],
    "retention_milestones": [
        Trigger.BIRTHDAY_REACHED,
        Trigger.WINBACK_INACTIVITY,
    ],
}

TRIGGER_LABELS: dict[Trigger, str] = {
    Trigger.USER_REGISTERED: "Inscription",
    Trigger.USER_LOGIN_DAILY: "Connexion quotidienne",
    Trigger.NEWSLETTER_SUBSCRIBED: "Abonnement newsletter",
    Trigger.PROFILE_COMPLETED: "Profil complété",
    Trigger.FIRST_PURCHASE: "Premier achat",
    Trigger.PURCHASE_MADE: "Achat effectué",
    Trigger.ORDER_VALUE_MILESTONE: "Seuil de montant de commande",
    Trigger.PRODUCT_PURCHASED: "Produit acheté",
    Trigger.CATEGORY_PURCHASED: "Catégorie achetée",
    Trigger.REVIEW_CREATED: "Avis produit déposé",
    Trigger.FRIEND_REFERRED: "Parrainage d'ami",
    Trigger.SOCIAL_SHARED: "Partage sur réseau social",
    Trigger.BIRTHDAY_REACHED: "Anniversaire",
    Trigger.WINBACK_INACTIVITY: "Retour après inactivité",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleEvaluation:
    triggered: bool
    points: int
    rule_id: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PointAward:
    user_id: int
    points: int
    reason: str
    rule_id: int | None = None
    reference_type: str | None = None
    reference_id: str | None = None


class RuleEngine:
    """Évalue un déclencheur contre toutes les règles actives et retourne les points à attribuer."""

    def __init__(self, *, rules: list[LoyaltyRuleDTO], now: datetime) -> None:
        self._rules = rules
        self._now = now

    def evaluate(self, trigger: Trigger, context: dict[str, Any]) -> list[PointAward]:
        awards: list[PointAward] = []
        for rule in self._rules:
            if not rule.is_active or rule.trigger != trigger:
                continue
            if not self._conditions_met(rule, context):
                continue
            if not self._limits_ok():
                continue
            awards.append(
                PointAward(
                    user_id=context["user_id"],
                    points=rule.points_value,
                    reason=rule.name,
                    rule_id=rule.id,
                    reference_type=context.get("reference_type"),
                    reference_id=context.get("reference_id"),
                )
            )
        return awards

    def _conditions_met(self, rule: LoyaltyRuleDTO, context: dict[str, Any]) -> bool:
        condition = rule.condition or {}
        if not condition:
            return True
        return all(
            [
                self._min_amount_ok(condition, context),
                self._product_ok(condition, context),
                self._category_ok(condition, context),
                self._photo_ok(condition, context),
                self._birthday_ok(rule, context),
                self._inactivity_ok(condition, context),
            ]
        )

    def _min_amount_ok(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        if "min_amount" not in condition:
            return True
        amount = context.get("order_amount")
        min_amount = condition["min_amount"]
        return amount is not None and amount >= min_amount

    def _product_ok(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        if "product_id" not in condition:
            return True
        return bool(context.get("product_id") == condition["product_id"])

    def _category_ok(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        if "category_id" not in condition:
            return True
        return bool(context.get("category_id") == condition["category_id"])

    def _photo_ok(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        if not condition.get("photo_required"):
            return True
        return bool(context.get("has_photo"))

    def _birthday_ok(self, rule: LoyaltyRuleDTO, context: dict[str, Any]) -> bool:
        if rule.trigger != Trigger.BIRTHDAY_REACHED:
            return True
        birthdate = context.get("birthdate")
        if birthdate is None:
            return False
        try:
            bd = datetime.fromisoformat(birthdate) if isinstance(birthdate, str) else birthdate
        except (ValueError, TypeError):
            return False
        return bd.month == self._now.month and bd.day == self._now.day

    def _inactivity_ok(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        if "days_inactive" not in condition:
            return True
        last_activity = context.get("last_activity")
        if last_activity is None:
            return False
        try:
            la = (
                datetime.fromisoformat(last_activity)
                if isinstance(last_activity, str)
                else last_activity
            )
        except (ValueError, TypeError):
            return False
        days_inactive = condition["days_inactive"]
        return (self._now - la).days >= int(days_inactive)

    def _limits_ok(self) -> bool:
        return True


@dataclass(frozen=True, slots=True, kw_only=True)
class LoyaltyRuleDTO:
    id: int
    name: str
    trigger: Trigger
    condition: dict[str, Any]
    action_type: str
    points_value: int
    is_active: bool
    max_per_user: int | None
    max_per_day: int | None
    cooldown_days: int | None
