from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.orders.domain.pricing import CouponKind
from core.api.fields import MAX_INTEGER


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class ZoneInput(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=80)
    fee = money(min_value=Decimal(0))
    cities = serializers.ListField(
        child=serializers.CharField(max_length=120), required=False, default=list
    )
    free_threshold = money(min_value=Decimal(0), required=False, allow_null=True, default=None)
    delivery_estimate = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    is_default = serializers.BooleanField(default=False)
    is_active = serializers.BooleanField(default=True)
    position = serializers.IntegerField(min_value=0, max_value=32767, default=0)

    def validate_cities(self, value: list[str]) -> tuple[str, ...]:
        return tuple(value)


class ZoneOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    cities = serializers.ListField(child=serializers.CharField())
    fee = money()
    free_threshold = money(allow_null=True)
    delivery_estimate = serializers.CharField()
    is_default = serializers.BooleanField()
    is_active = serializers.BooleanField()
    position = serializers.IntegerField()


class CouponInput(serializers.Serializer[Any]):
    code = serializers.RegexField(r"^[A-Za-z0-9_-]{3,40}$")
    kind = serializers.ChoiceField(choices=[item.value for item in CouponKind])
    value = money(min_value=Decimal("0.01"))
    description = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    max_discount = money(min_value=Decimal("0.01"), required=False, allow_null=True, default=None)
    min_subtotal = money(min_value=Decimal(0), required=False, default=Decimal(0))
    free_shipping = serializers.BooleanField(default=False)
    starts_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    usage_limit = serializers.IntegerField(
        max_value=MAX_INTEGER, min_value=1, required=False, allow_null=True, default=None
    )
    per_user_limit = serializers.IntegerField(
        max_value=MAX_INTEGER, min_value=1, required=False, allow_null=True, default=None
    )
    is_active = serializers.BooleanField(default=True)

    def validate_kind(self, value: str) -> CouponKind:
        return CouponKind(value)


class CouponFiltersInput(serializers.Serializer[Any]):
    search = serializers.CharField(max_length=40, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False, allow_null=True, default=None)


class CouponOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    code = serializers.CharField()
    description = serializers.CharField()
    kind = serializers.CharField()
    value = money()
    max_discount = money(allow_null=True)
    min_subtotal = money()
    free_shipping = serializers.BooleanField()
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    usage_limit = serializers.IntegerField(allow_null=True)
    per_user_limit = serializers.IntegerField(allow_null=True)
    is_active = serializers.BooleanField()
    uses = serializers.IntegerField()
    discount_total = money()
    created_at = serializers.DateTimeField()
