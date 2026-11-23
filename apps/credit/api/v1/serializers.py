from typing import Any

from rest_framework import serializers

from apps.credit.domain.rules import EntryKind


def money() -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2)


class MovementOutput(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=[kind.value for kind in EntryKind])
    kind_label = serializers.SerializerMethodField()
    amount = money()
    at = serializers.DateTimeField()
    order_number = serializers.CharField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField()

    def get_kind_label(self, movement: Any) -> str:
        return str(EntryKind(movement.kind).label)


class StoreCreditOutput(serializers.Serializer[Any]):
    available = money()
    next_expiry = serializers.DateTimeField(allow_null=True)
    history = MovementOutput(many=True)
