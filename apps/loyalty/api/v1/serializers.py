from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.loyalty.domain.rules import Trigger


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class LoyaltySettingsInput(serializers.Serializer[Any]):
    cashback_enabled = serializers.BooleanField()
    cashback_members_only = serializers.BooleanField()
    cashback_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.01"), max_value=Decimal("50")
    )
    cashback_max_share = serializers.IntegerField(min_value=1, max_value=100)
    cashback_min_balance = money(min_value=Decimal("0"))
    cashback_validity_months = serializers.IntegerField(min_value=1, max_value=60)
    app_store_url = serializers.URLField(max_length=300, allow_blank=True)
    play_store_url = serializers.URLField(max_length=300, allow_blank=True)


class CashbackTermsOutput(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    members_only = serializers.BooleanField()
    percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    max_share = serializers.IntegerField()
    min_balance = money()
    validity_months = serializers.IntegerField()


class AppLinksOutput(serializers.Serializer[Any]):
    app_store = serializers.CharField()
    play_store = serializers.CharField()


class ProgrammesOutput(serializers.Serializer[Any]):
    cashback = CashbackTermsOutput()
    app_links = AppLinksOutput()


class LoyaltyRuleInput(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150)
    trigger = serializers.ChoiceField(choices=[item.value for item in Trigger])
    condition = serializers.JSONField(default=dict, required=False)
    points_value = serializers.IntegerField()
    is_active = serializers.BooleanField(default=True)
    max_per_user = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    max_per_day = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    cooldown_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class LoyaltyRuleOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    trigger = serializers.CharField()
    condition = serializers.JSONField()
    action_type = serializers.CharField()
    points_value = serializers.IntegerField()
    is_active = serializers.BooleanField()
    max_per_user = serializers.IntegerField(allow_null=True)
    max_per_day = serializers.IntegerField(allow_null=True)
    cooldown_days = serializers.IntegerField(allow_null=True)


class PointBalanceOutput(serializers.Serializer[Any]):
    total = serializers.IntegerField()
    available = serializers.IntegerField()
    pending = serializers.IntegerField()


class PointTransactionOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    points = serializers.IntegerField()
    reason = serializers.CharField()
    rule_id = serializers.IntegerField(allow_null=True)
    rule_name = serializers.CharField(allow_null=True)
    reference_type = serializers.CharField(allow_null=True)
    reference_id = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class BalanceOutput(serializers.Serializer[Any]):
    eligible = serializers.BooleanField()
    available = money()
    pending = money()
    next_expiry = serializers.DateTimeField(allow_null=True)
