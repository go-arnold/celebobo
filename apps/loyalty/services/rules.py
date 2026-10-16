from __future__ import annotations

from typing import Any

from apps.loyalty.domain.points import PointTransactionView
from apps.loyalty.domain.rules import LoyaltyRuleDTO, RuleEngine, Trigger
from apps.loyalty.models import LoyaltyRule
from apps.loyalty.repositories import LoyaltyRuleRepository, PointTransactionRepository
from apps.loyalty.selectors import to_point_transaction_view


class LoyaltyRuleService:
    def __init__(
        self,
        *,
        rules: LoyaltyRuleRepository,
        transactions: PointTransactionRepository,
    ) -> None:
        self._rules = rules
        self._transactions = transactions

    def list(self, *, is_active: bool | None = None) -> list[LoyaltyRuleDTO]:
        return [self._to_dto(rule) for rule in self._rules.list(is_active=is_active)]

    def get(self, rule_id: int) -> LoyaltyRule | None:
        return self._rules.get(rule_id)

    def create(
        self,
        *,
        name: str,
        trigger: str,
        condition: dict,
        points_value: int,
        is_active: bool = True,
        max_per_user: int | None = None,
        max_per_day: int | None = None,
        cooldown_days: int | None = None,
    ) -> LoyaltyRule:
        return self._rules.create(
            name=name,
            trigger=trigger,
            condition=condition,
            action_type="add_points",
            points_value=points_value,
            is_active=is_active,
            max_per_user=max_per_user,
            max_per_day=max_per_day,
            cooldown_days=cooldown_days,
        )

    def update(self, rule_id: int, **changes: Any) -> LoyaltyRule:
        rule = self._rules.get(rule_id)
        if rule is None:
            from apps.loyalty.domain.errors import RuleNotFound

            raise RuleNotFound
        for field, value in changes.items():
            setattr(rule, field, value)
        self._rules.update(rule, fields=tuple(changes.keys()))
        return rule

    def delete(self, rule_id: int) -> None:
        rule = self._rules.get(rule_id)
        if rule is None:
            from apps.loyalty.domain.errors import RuleNotFound

            raise RuleNotFound
        self._rules.delete(rule)

    def to_dto(self, rule: LoyaltyRule) -> LoyaltyRuleDTO:
        return LoyaltyRuleDTO(
            id=rule.pk,
            name=rule.name,
            trigger=Trigger(rule.trigger),
            condition=rule.condition,
            action_type=rule.action_type,
            points_value=rule.points_value,
            is_active=rule.is_active,
            max_per_user=rule.max_per_user,
            max_per_day=rule.max_per_day,
            cooldown_days=rule.cooldown_days,
        )

    def evaluate_trigger(
        self, *, trigger: Trigger, user_id: int, now, context: dict
    ) -> list[PointTransactionView]:
        rules = self._rules.list(is_active=True)
        dtos = [self._to_dto(rule) for rule in rules]
        engine = RuleEngine(rules=dtos, now=now)
        awards = engine.evaluate(trigger, {**context, "user_id": user_id})
        created: list[PointTransactionView] = []
        for award in awards:
            tx = self._transactions.add(
                user_id=award.user_id,
                points=award.points,
                reason=award.reason,
                rule_id=award.rule_id,
                reference_type=award.reference_type,
                reference_id=award.reference_id,
            )
            created.append(to_point_transaction_view(tx))
        return created
