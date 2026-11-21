from decimal import Decimal
from typing import Any

from rest_framework import serializers


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class LoyaltySettingsInput(serializers.Serializer[Any]):
    points_enabled = serializers.BooleanField()
    points_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.01"), max_value=Decimal("50")
    )
    points_validity_months = serializers.IntegerField(min_value=1, max_value=60)
    app_store_url = serializers.URLField(max_length=300, allow_blank=True)
    play_store_url = serializers.URLField(max_length=300, allow_blank=True)


class PointsTermsOutput(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    validity_months = serializers.IntegerField()


class AppLinksOutput(serializers.Serializer[Any]):
    app_store = serializers.CharField()
    play_store = serializers.CharField()


class ProgrammesOutput(serializers.Serializer[Any]):
    points = PointsTermsOutput()
    app_links = AppLinksOutput()


class MovementOutput(serializers.Serializer[Any]):
    kind = serializers.CharField()
    amount = money()
    at = serializers.DateTimeField()
    order_number = serializers.CharField(allow_null=True)
    pending = serializers.BooleanField()


class BalanceOutput(serializers.Serializer[Any]):
    eligible = serializers.BooleanField()
    available = money()
    pending = money()
    next_expiry = serializers.DateTimeField(allow_null=True)
    closes_at = serializers.DateTimeField(allow_null=True)
    orders_count = serializers.IntegerField()
    orders_total = money()
    history = MovementOutput(many=True)
