from typing import Any

from rest_framework import serializers

from apps.accounts.api.v1.serializers import PHONE_ERROR, PHONE_PATTERN
from apps.accounts.domain.enums import ACCOUNT_ROLES
from core.domain.actor import Role

ROLE_CHOICES = [role.value for role in ACCOUNT_ROLES]


class UserFiltersInput(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=ROLE_CHOICES, required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False, allow_null=True, default=None)

    def validate_role(self, value: str) -> Role:
        return Role(value)


class EditUserInput(serializers.Serializer[Any]):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.RegexField(
        PHONE_PATTERN, error_messages=PHONE_ERROR, allow_null=True
    )


class CreateUserInput(EditUserInput):
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    phone_number = serializers.RegexField(
        PHONE_PATTERN, error_messages=PHONE_ERROR, required=False, allow_null=True
    )

    def validate_role(self, value: str) -> Role:
        return Role(value)


class InviterOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    referral_code = serializers.CharField(allow_null=True)


class UserRowOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField()
    phone_number = serializers.CharField(allow_null=True)
    avatar = serializers.CharField()
    role = serializers.CharField(source="role.value")
    referral_code = serializers.CharField(allow_null=True)
    invited_by = InviterOutput(allow_null=True)
    is_active = serializers.BooleanField()
    email_verified = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)
