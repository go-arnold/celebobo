from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.accounts.domain.enums import MAX_COMMISSION_RATE, ResellerOrdering
from apps.resellers.domain.enums import ApplicationStatus

PHONE_PATTERN = r"^\+?[\d\s().-]{7,20}$"


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=12, decimal_places=2, **options)


def rate(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=4, decimal_places=3, **options)


class SubmitApplicationInput(serializers.Serializer[Any]):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField()
    phone_number = serializers.RegexField(
        PHONE_PATTERN, error_messages={"invalid": "Numéro de téléphone invalide."}
    )
    city = serializers.CharField(max_length=120)
    message = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ApplicationFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[item.value for item in ApplicationStatus], required=False
    )
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_status(self, value: str) -> ApplicationStatus:
        return ApplicationStatus(value)


class ApproveApplicationInput(serializers.Serializer[Any]):
    commission_rate = rate(
        min_value=Decimal(0), max_value=MAX_COMMISSION_RATE, required=False, allow_null=True
    )
    manager_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class RejectApplicationInput(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ResellerFiltersInput(serializers.Serializer[Any]):
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False, allow_null=True, default=None)
    manager_id = serializers.IntegerField(min_value=1, required=False)
    ordering = serializers.ChoiceField(
        choices=[item.value for item in ResellerOrdering], required=False
    )

    def validate_ordering(self, value: str) -> ResellerOrdering:
        return ResellerOrdering(value)


class ResellerChangesInput(serializers.Serializer[Any]):
    commission_rate = rate(min_value=Decimal(0), max_value=MAX_COMMISSION_RATE)
    manager_id = serializers.IntegerField(min_value=1, allow_null=True)


class ResellerPersonOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ApplicationReceiptOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    status = serializers.CharField(source="status.value")
    created_at = serializers.DateTimeField()


class ApplicationOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    phone_number = serializers.CharField()
    city = serializers.CharField()
    message = serializers.CharField()
    status = serializers.CharField(source="status.value")
    applicant_id = serializers.IntegerField(allow_null=True)
    reseller_id = serializers.IntegerField(allow_null=True)
    reviewed_by = ResellerPersonOutput(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    decision_note = serializers.CharField()
    created_at = serializers.DateTimeField()


class PerformanceOutput(serializers.Serializer[Any]):
    sales_count = serializers.IntegerField()
    revenue = money()
    commission_earned = money()
    commission_due = money()


class ResellerOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField(source="account.id")
    first_name = serializers.CharField(source="account.first_name")
    last_name = serializers.CharField(source="account.last_name")
    name = serializers.CharField(source="account.name")
    email = serializers.EmailField(source="account.email")
    phone_number = serializers.CharField(source="account.phone_number", allow_null=True)
    avatar = serializers.CharField(source="account.avatar")
    referral_code = serializers.CharField(source="account.referral_code", allow_null=True)
    commission_rate = rate(source="account.commission_rate")
    availability = serializers.CharField(source="account.availability.value")
    is_active = serializers.BooleanField(source="account.is_active")
    manager = ResellerPersonOutput(source="account.manager", allow_null=True)
    date_joined = serializers.DateTimeField(source="account.date_joined")
    last_seen_at = serializers.DateTimeField(source="account.last_seen_at", allow_null=True)
    invited_count = serializers.IntegerField(source="account.invited_count")
    performance = PerformanceOutput()


class TopResellerOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    revenue = money()


class ResellerStatsOutput(serializers.Serializer[Any]):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    invited_clients = serializers.IntegerField()
    pending_applications = serializers.IntegerField()
    period_days = serializers.IntegerField()
    top_reseller = TopResellerOutput(allow_null=True)


class InviteeOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    joined_at = serializers.DateTimeField()
    orders_count = serializers.IntegerField()
    orders_total = money()


class InviteesSummaryOutput(serializers.Serializer[Any]):
    code = serializers.CharField(allow_null=True)
    invited_count = serializers.IntegerField()
    orders_total = money()


class ReferralKitOutput(serializers.Serializer[Any]):
    code = serializers.CharField()
    link = serializers.URLField()
    qr_svg = serializers.CharField()
    share_text = serializers.CharField()
    whatsapp_url = serializers.URLField()
