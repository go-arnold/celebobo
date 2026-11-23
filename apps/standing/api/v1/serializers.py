from typing import Any

from rest_framework import serializers

from apps.standing.domain.rules import SanctionKind, SanctionStatus


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=12, decimal_places=2, **options)


def score(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=3, decimal_places=1, **options)


class StandingFiltersInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, required=False)


class SanctionFiltersInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, required=False)
    status = serializers.ChoiceField(
        choices=[status.value for status in SanctionStatus], required=False
    )


class OpenSanctionInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=[kind.value for kind in SanctionKind])
    reason = serializers.CharField(max_length=2000)
    days = serializers.IntegerField(min_value=1, max_value=365, required=False, allow_null=True)
    urgent = serializers.BooleanField(required=False, default=False)

    def validate_kind(self, value: str) -> SanctionKind:
        return SanctionKind(value)


class ExplainSanctionInput(serializers.Serializer[Any]):
    explanation = serializers.CharField(max_length=4000)


class DecideSanctionInput(serializers.Serializer[Any]):
    apply = serializers.BooleanField()
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class SanctionOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    reseller_id = serializers.IntegerField()
    reseller_name = serializers.CharField()
    kind = serializers.ChoiceField(choices=[kind.value for kind in SanctionKind])
    kind_label = serializers.SerializerMethodField()
    reason = serializers.CharField()
    urgent = serializers.BooleanField()
    days = serializers.IntegerField(allow_null=True)
    status = serializers.ChoiceField(choices=[status.value for status in SanctionStatus])
    explain_until = serializers.DateTimeField(allow_null=True)
    explanation = serializers.CharField()
    explained_at = serializers.DateTimeField(allow_null=True)
    decision_note = serializers.CharField()
    decided_at = serializers.DateTimeField(allow_null=True)
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    active = serializers.BooleanField()

    def get_kind_label(self, sanction: Any) -> str:
        return str(SanctionKind(sanction.kind).label)


class StandingOutput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField()
    reseller_name = serializers.CharField()
    level = serializers.CharField()
    level_label = serializers.SerializerMethodField()
    advantages = serializers.CharField()
    sales = money()
    rating = score(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    next_level = serializers.CharField(allow_null=True)
    next_sales = money(allow_null=True)
    next_rating = score(allow_null=True)
    suspended_until = serializers.DateTimeField(allow_null=True)
    sanctions = SanctionOutput(many=True)

    def get_level_label(self, standing: Any) -> str:
        return str(standing.level.label)


class LevelReviewOutput(serializers.Serializer[Any]):
    changed = serializers.IntegerField()
