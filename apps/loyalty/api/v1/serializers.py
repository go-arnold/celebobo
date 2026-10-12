from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.loyalty.domain.membership import MembershipStatus, Plan, RequestStatus
from apps.orders.domain.enums import PaymentMethod


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class LoyaltySettingsInput(serializers.Serializer[Any]):
    membership_enabled = serializers.BooleanField()
    membership_monthly_price = money(min_value=Decimal("0.01"))
    membership_yearly_price = money(min_value=Decimal("0.01"))
    membership_trial_days = serializers.IntegerField(min_value=0, max_value=365)
    membership_reminder_days = serializers.IntegerField(min_value=0, max_value=30)
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


class MembershipTermsOutput(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    monthly_price = money()
    yearly_price = money()
    trial_days = serializers.IntegerField()
    reminder_days = serializers.IntegerField()


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
    membership = MembershipTermsOutput()
    cashback = CashbackTermsOutput()
    app_links = AppLinksOutput()


class MembershipRequestInput(serializers.Serializer[Any]):
    plan = serializers.ChoiceField(choices=[Plan.MONTHLY.value, Plan.YEARLY.value])
    payment_method = serializers.ChoiceField(choices=[item.value for item in PaymentMethod])

    def validate_plan(self, value: str) -> Plan:
        return Plan(value)


class RejectInput(serializers.Serializer[Any]):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class RequestFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=[item.value for item in RequestStatus], required=False)


class MemberFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[item.value for item in MembershipStatus if item is not MembershipStatus.NONE],
        required=False,
    )


class RequestOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    plan = serializers.ChoiceField(choices=[item.value for item in Plan])
    price = money()
    payment_method = serializers.CharField()
    status = serializers.ChoiceField(choices=[item.value for item in RequestStatus])
    note = serializers.CharField()
    created_at = serializers.DateTimeField()
    handled_at = serializers.DateTimeField(allow_null=True)


class MemberOutput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=[item.value for item in MembershipStatus])
    plan = serializers.ChoiceField(choices=[item.value for item in Plan], allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    trial_available = serializers.BooleanField()
    pending_request = RequestOutput(allow_null=True)


class MemberRefOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()


class AdminRequestOutput(serializers.Serializer[Any]):
    member = MemberRefOutput()

    def to_representation(self, instance: Any) -> dict[str, Any]:
        return {**RequestOutput(instance.request).data, **super().to_representation(instance)}


class AdminMemberOutput(serializers.Serializer[Any]):
    member = MemberRefOutput()
    status = serializers.ChoiceField(choices=[item.value for item in MembershipStatus])
    plan = serializers.ChoiceField(choices=[item.value for item in Plan])
    ends_at = serializers.DateTimeField()


class BalanceOutput(serializers.Serializer[Any]):
    eligible = serializers.BooleanField()
    available = money()
    pending = money()
    next_expiry = serializers.DateTimeField(allow_null=True)
