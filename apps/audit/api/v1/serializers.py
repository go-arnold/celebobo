from typing import Any

from rest_framework import serializers

from apps.audit.domain.enums import AuditAction


class DateRangeInput(serializers.Serializer[Any]):
    date = serializers.DateField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    actor_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        day = attrs.pop("date", None)
        if day is not None:
            attrs["date_from"] = attrs["date_to"] = day
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end and start > end:
            raise serializers.ValidationError({"date_to": ["Doit suivre la date de début."]})
        return attrs


class ChangeFiltersInput(DateRangeInput):
    action = serializers.ChoiceField(choices=[item.value for item in AuditAction], required=False)
    object_type = serializers.RegexField(r"^[a-z_]+\.[a-z_]+$", required=False)
    object_id = serializers.CharField(max_length=64, required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_action(self, value: str) -> AuditAction:
        return AuditAction(value)


class EventFiltersInput(DateRangeInput):
    event_type = serializers.CharField(max_length=160, required=False)


class AuditActorOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ChangeOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    action = serializers.CharField(source="action.value")
    object_type = serializers.CharField()
    object_id = serializers.CharField()
    object_repr = serializers.CharField()
    changes = serializers.JSONField()
    actor = AuditActorOutput(allow_null=True)
    remote_addr = serializers.CharField(allow_null=True)


class EventOutput(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    event_type = serializers.CharField()
    name = serializers.CharField()
    actor = AuditActorOutput(allow_null=True)
    payload = serializers.JSONField()
    occurred_at = serializers.DateTimeField()


class TrackedTypeOutput(serializers.Serializer[Any]):
    key = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
