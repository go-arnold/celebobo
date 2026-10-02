from typing import Any

from rest_framework import serializers

from apps.push.domain.messages import RegisterDevice


class SubscriptionKeysInput(serializers.Serializer[Any]):
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=100)


class RegisterDeviceInput(serializers.Serializer[Any]):
    endpoint = serializers.URLField(max_length=1000)
    keys = SubscriptionKeysInput()
    user_agent = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_endpoint(self, value: str) -> str:
        if not value.startswith("https://"):
            raise serializers.ValidationError("Le point d'accès doit être en HTTPS.")
        return value

    def validate(self, attrs: dict[str, Any]) -> RegisterDevice:
        return RegisterDevice(
            endpoint=attrs["endpoint"],
            p256dh=attrs["keys"]["p256dh"],
            auth=attrs["keys"]["auth"],
            user_agent=attrs.get("user_agent", ""),
        )


class DeviceOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    user_agent = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)


class PublicKeyOutput(serializers.Serializer[Any]):
    public_key = serializers.CharField()
    enabled = serializers.BooleanField()
