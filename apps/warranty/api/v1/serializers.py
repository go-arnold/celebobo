from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.warranty.domain.rules import ClaimKind, ClaimStatus, Outcome, ReturnMethod

KINDS = [kind.value for kind in ClaimKind]


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


def note() -> serializers.CharField:
    return serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class SubmitClaimInput(serializers.Serializer[Any]):
    order_id = serializers.IntegerField(min_value=1)
    item_id = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=KINDS)
    description = serializers.CharField(max_length=2000)
    serial = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    photos = serializers.ListField(
        child=serializers.URLField(max_length=500), max_length=6, required=False, default=list
    )

    def validate_kind(self, value: str) -> ClaimKind:
        return ClaimKind(value)

    def validate_photos(self, value: list[str]) -> tuple[str, ...]:
        return tuple(value)


class AnswerClaimInput(serializers.Serializer[Any]):
    return_method = serializers.ChoiceField(choices=[method.value for method in ReturnMethod])
    note = note()

    def validate_return_method(self, value: str) -> ReturnMethod:
        return ReturnMethod(value)


class ReceiveClaimInput(serializers.Serializer[Any]):
    sealed = serializers.BooleanField(required=False, allow_null=True, default=None)
    note = note()


class DiagnoseClaimInput(serializers.Serializer[Any]):
    covered = serializers.BooleanField()
    outcome = serializers.ChoiceField(choices=[outcome.value for outcome in Outcome])
    note = note()
    new_serial = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    quote = money(min_value=Decimal(0), required=False, allow_null=True, default=None)

    def validate_outcome(self, value: str) -> Outcome:
        return Outcome(value)


class FinishRepairInput(serializers.Serializer[Any]):
    note = note()


class ClaimFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[status.value for status in ClaimStatus], required=False
    )


class ClaimableLineOutput(serializers.Serializer[Any]):
    order_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    name = serializers.CharField()
    serials = serializers.ListField(child=serializers.CharField())
    kinds = serializers.ListField(child=serializers.ChoiceField(choices=KINDS))
    trial_until = serializers.DateField(allow_null=True)
    warranty_until = serializers.DateField(allow_null=True)
    authenticity_until = serializers.DateField()
    open_claim_id = serializers.IntegerField(allow_null=True)


class ClaimOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    number = serializers.CharField()
    order_id = serializers.IntegerField()
    order_number = serializers.CharField()
    item_id = serializers.IntegerField()
    product_name = serializers.CharField()
    serial = serializers.CharField()
    client_id = serializers.IntegerField()
    client_name = serializers.CharField()
    kind = serializers.ChoiceField(choices=KINDS)
    kind_label = serializers.SerializerMethodField()
    protection = serializers.CharField()
    description = serializers.CharField()
    photos = serializers.ListField(child=serializers.CharField())
    status = serializers.ChoiceField(choices=[status.value for status in ClaimStatus])
    created_at = serializers.DateTimeField()
    answer_due = serializers.DateTimeField()
    return_method = serializers.CharField(allow_null=True)
    answer_note = serializers.CharField()
    answered_at = serializers.DateTimeField(allow_null=True)
    received_at = serializers.DateTimeField(allow_null=True)
    sealed = serializers.BooleanField(allow_null=True)
    diagnosis_due = serializers.DateTimeField(allow_null=True)
    covered = serializers.BooleanField(allow_null=True)
    outcome = serializers.CharField(allow_null=True)
    diagnosis_note = serializers.CharField()
    diagnosed_at = serializers.DateTimeField(allow_null=True)
    outcome_due = serializers.DateTimeField(allow_null=True)
    new_serial = serializers.CharField()
    quote = money(allow_null=True)
    exchange_warranty_until = serializers.DateField(allow_null=True)
    repaired_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    overdue = serializers.BooleanField()

    def get_kind_label(self, claim: Any) -> str:
        return str(ClaimKind(claim.kind).label)
