from decimal import Decimal
from typing import Any

from rest_framework import serializers


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class LoyaltySettingsInput(serializers.Serializer[Any]):
    membership_enabled = serializers.BooleanField()
    membership_monthly_price = money(min_value=Decimal("0.01"))
    membership_yearly_price = money(min_value=Decimal("0.01"))
    membership_trial_days = serializers.IntegerField(min_value=0, max_value=365)
    membership_reminder_days = serializers.IntegerField(min_value=0, max_value=30)
    cashback_enabled = serializers.BooleanField()
    cashback_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.01"), max_value=Decimal("50")
    )
    cashback_max_share = serializers.IntegerField(min_value=1, max_value=100)
    cashback_min_balance = money(min_value=Decimal("0"))
    cashback_validity_months = serializers.IntegerField(min_value=1, max_value=60)
    app_store_url = serializers.URLField(max_length=300, allow_blank=True)
    play_store_url = serializers.URLField(max_length=300, allow_blank=True)


class MembershipTermsOutput(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    monthly_price = money()
    yearly_price = money()
    trial_days = serializers.IntegerField()
    reminder_days = serializers.IntegerField()


class CashbackTermsOutput(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    max_share = serializers.IntegerField()
    min_balance = money()
    validity_months = serializers.IntegerField()


class AppLinksOutput(serializers.Serializer[Any]):
    app_store = serializers.CharField()
    play_store = serializers.CharField()


class ProgrammesOutput(serializers.Serializer[Any]):
    membership = MembershipTermsOutput()
    cashback = CashbackTermsOutput()
    app_links = AppLinksOutput()
