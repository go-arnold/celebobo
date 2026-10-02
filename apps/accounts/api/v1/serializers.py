from typing import Any

from django_stubs_ext import StrPromise
from rest_framework import serializers

from apps.accounts.domain.enums import (
    ACCOUNT_ROLES,
    AddressLabel,
    Availability,
    NotificationChannel,
    NotificationTopic,
)
from core.api.fields import MAX_INTEGER
from core.domain.actor import Role

PHONE_PATTERN = r"^\+?[\d\s().-]{7,20}$"
REFERRAL_PATTERN = r"^\d{4}$"
REFERRAL_ERROR: dict[str, str | StrPromise] = {
    "invalid": "Le code revendeur doit contenir 4 chiffres."
}
PHONE_ERROR: dict[str, str | StrPromise] = {"invalid": "Numéro de téléphone invalide."}


class RegisterInput(serializers.Serializer[Any]):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)
    phone_number = serializers.RegexField(
        PHONE_PATTERN, required=False, allow_null=True, error_messages=PHONE_ERROR
    )
    referral_code = serializers.RegexField(
        REFERRAL_PATTERN, required=False, allow_null=True, error_messages=REFERRAL_ERROR
    )


class RegistrationOutput(serializers.Serializer[Any]):
    user_id = serializers.IntegerField()
    email = serializers.EmailField()
    verification_required = serializers.BooleanField()


class UpdateProfileInput(serializers.Serializer[Any]):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.RegexField(
        PHONE_PATTERN, allow_null=True, error_messages=PHONE_ERROR
    )
    avatar_upload_id = serializers.IntegerField(min_value=1, allow_null=True, max_value=MAX_INTEGER)
    referral_code = serializers.RegexField(REFERRAL_PATTERN, error_messages=REFERRAL_ERROR)


class ResellerProfileOutput(serializers.Serializer[Any]):
    referral_code = serializers.CharField(allow_null=True)
    availability = serializers.ChoiceField(choices=[item.value for item in Availability])
    commission_rate = serializers.DecimalField(max_digits=4, decimal_places=3)
    invited_count = serializers.IntegerField()


class ProfileOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone_number = serializers.CharField(allow_null=True)
    avatar = serializers.CharField()
    role = serializers.ChoiceField(choices=[role.value for role in ACCOUNT_ROLES])
    email_verified = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    invited_by_code = serializers.CharField(allow_null=True)
    permissions = serializers.ListField(child=serializers.CharField())
    reseller = ResellerProfileOutput(allow_null=True)


class AddressPatchInput(serializers.Serializer[Any]):
    label = serializers.ChoiceField(choices=[item.value for item in AddressLabel])  # type: ignore[assignment]
    recipient = serializers.CharField(max_length=120)
    phone = serializers.RegexField(PHONE_PATTERN, error_messages=PHONE_ERROR)
    line1 = serializers.CharField(max_length=255)
    quarter = serializers.CharField(max_length=120)
    city = serializers.CharField(max_length=120)
    country = serializers.CharField(max_length=80)

    def validate_label(self, value: str) -> AddressLabel:
        return AddressLabel(value)


class AddressInput(AddressPatchInput):
    is_default = serializers.BooleanField(default=False)


class AddressOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    label = serializers.CharField()  # type: ignore[assignment]
    recipient = serializers.CharField()
    phone = serializers.CharField()
    line1 = serializers.CharField()
    quarter = serializers.CharField()
    city = serializers.CharField()
    country = serializers.CharField()
    is_default = serializers.BooleanField()


class ChannelToggles(serializers.Serializer[Any]):
    email = serializers.BooleanField(required=False)
    push = serializers.BooleanField(required=False)


class PreferencesInput(serializers.Serializer[Any]):
    order_assigned = ChannelToggles(required=False)
    status_changed = ChannelToggles(required=False)
    new_message = ChannelToggles(required=False)
    promotions = ChannelToggles(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return {
            "preferences": {
                NotificationTopic(topic): {
                    NotificationChannel(channel): enabled for channel, enabled in toggles.items()
                }
                for topic, toggles in attrs.items()
            }
        }


class PreferencesOutput(serializers.Serializer[Any]):
    order_assigned = ChannelToggles()
    status_changed = ChannelToggles()
    new_message = ChannelToggles()
    promotions = ChannelToggles()


class ChangeRoleInput(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=[role.value for role in ACCOUNT_ROLES])

    def validate_role(self, value: str) -> Role:
        return Role(value)


class AvailabilityInput(serializers.Serializer[Any]):
    availability = serializers.ChoiceField(choices=[item.value for item in Availability])

    def validate_availability(self, value: str) -> Availability:
        return Availability(value)


class ReferralCheckOutput(serializers.Serializer[Any]):
    valid = serializers.BooleanField()
    reseller_first_name = serializers.CharField(allow_null=True)


class WsTicketOutput(serializers.Serializer[Any]):
    ticket = serializers.CharField()
    expires_in = serializers.IntegerField()
