from typing import Any

from rest_framework import serializers

from apps.cagnotte.domain.rules import CampaignKind, Payout, RewardStatus


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class CampaignInputSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(
        max_length=4000, required=False, allow_blank=True, default=""
    )
    kind = serializers.ChoiceField(choices=[kind.value for kind in CampaignKind])
    percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    min_purchase = money(required=False, allow_null=True, default=None)
    cap = money(required=False, allow_null=True, default=None)
    payout = serializers.ChoiceField(
        choices=[payout.value for payout in Payout], required=False, default=Payout.POINTS.value
    )
    points_valid_days = serializers.IntegerField(required=False, default=90)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=100
    )
    product_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=500
    )

    def validate_kind(self, value: str) -> CampaignKind:
        return CampaignKind(value)

    def validate_payout(self, value: str) -> Payout:
        return Payout(value)


class RefOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()


class CampaignOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    kind = serializers.ChoiceField(choices=[kind.value for kind in CampaignKind])
    kind_label = serializers.SerializerMethodField()
    percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    min_purchase = money(allow_null=True)
    cap = money(allow_null=True)
    payout = serializers.ChoiceField(choices=[payout.value for payout in Payout], allow_null=True)
    points_valid_days = serializers.IntegerField(allow_null=True)
    categories = RefOutput(many=True)
    products = RefOutput(many=True)
    state = serializers.ChoiceField(choices=["upcoming", "running", "ended"])
    created_at = serializers.DateTimeField()

    def get_kind_label(self, campaign: Any) -> str:
        return str(CampaignKind(campaign.kind).label)


class CurrentCampaignOutput(serializers.Serializer[Any]):
    campaign = CampaignOutput(allow_null=True)


class RewardFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[status.value for status in RewardStatus], required=False
    )
    # the Mobile Money cashbacks to send now
    due = serializers.BooleanField(required=False, default=False)


class PayRewardInput(serializers.Serializer[Any]):
    reference = serializers.CharField(max_length=80)


class RewardOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    campaign_id = serializers.IntegerField()
    campaign_name = serializers.CharField()
    kind = serializers.ChoiceField(choices=[kind.value for kind in CampaignKind])
    payout = serializers.ChoiceField(choices=[payout.value for payout in Payout])
    order_id = serializers.IntegerField()
    order_number = serializers.CharField()
    client_id = serializers.IntegerField()
    client_name = serializers.CharField()
    phone = serializers.CharField()
    amount = money()
    kept = money()
    owed_back = money()
    status = serializers.ChoiceField(choices=[status.value for status in RewardStatus])
    available_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    reference = serializers.CharField()
    created_at = serializers.DateTimeField()


# the client's own: no phone, no name
class MyRewardOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    campaign_name = serializers.CharField()
    kind = serializers.ChoiceField(choices=[kind.value for kind in CampaignKind])
    payout = serializers.ChoiceField(choices=[payout.value for payout in Payout])
    order_number = serializers.CharField()
    amount = money()
    kept = money()
    status = serializers.ChoiceField(choices=[status.value for status in RewardStatus])
    available_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
