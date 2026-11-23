from decimal import Decimal
from typing import Any

from rest_framework import serializers


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class SummaryFiltersInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, required=False)


class RecordRemittanceInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1)
    amount = money(min_value=Decimal("0.01"))
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    received_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class CollectionOutput(serializers.Serializer[Any]):
    order_id = serializers.IntegerField()
    order_number = serializers.CharField()
    amount = money()
    left = money()
    collected_at = serializers.DateTimeField()
    due_at = serializers.DateTimeField()
    overdue = serializers.BooleanField()


class RemittanceOutput(serializers.Serializer[Any]):
    amount = money()
    reference = serializers.CharField()
    received_at = serializers.DateTimeField()


class CashSummaryOutput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField()
    reseller_name = serializers.CharField()
    level = serializers.CharField()
    cap = money()
    held = money()
    overdue = money()
    oldest_due = serializers.DateTimeField(allow_null=True)
    blocked_reason = serializers.CharField(allow_null=True)
    collections = CollectionOutput(many=True)
    remittances = RemittanceOutput(many=True)
