from typing import Any

from rest_framework import serializers

from apps.media.domain.policies import UploadPurpose
from core.api.fields import MAX_INTEGER

PURPOSES = [item.value for item in UploadPurpose]


class SignInput(serializers.Serializer[Any]):
    purpose = serializers.ChoiceField(choices=PURPOSES)


class CompleteInput(serializers.Serializer[Any]):
    purpose = serializers.ChoiceField(choices=PURPOSES)
    public_id = serializers.CharField(max_length=255)
    version = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    signature = serializers.RegexField(r"^[0-9a-f]{40}$")
    format = serializers.CharField(max_length=10)
    bytes = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    width = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    height = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )

    def validate_purpose(self, value: str) -> UploadPurpose:
        return UploadPurpose(value)


class SignatureOutput(serializers.Serializer[Any]):
    upload_url = serializers.URLField()
    cloud_name = serializers.CharField()
    api_key = serializers.CharField()
    timestamp = serializers.IntegerField()
    signature = serializers.CharField()
    folder = serializers.CharField()
    allowed_formats = serializers.CharField()
    transformation = serializers.CharField()
    max_bytes = serializers.IntegerField()


class MediaOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    purpose = serializers.CharField()
    public_id = serializers.CharField()
    url = serializers.URLField()
    format = serializers.CharField()
    bytes = serializers.IntegerField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
