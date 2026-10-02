from typing import Any

from rest_framework import serializers

from apps.assistant.domain.enums import Sentiment


class MessageInput(serializers.Serializer[Any]):
    content = serializers.CharField(max_length=4000, trim_whitespace=True)


class AssistantMessageOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    role = serializers.CharField(source="role.value")
    content = serializers.CharField()
    product_ids = serializers.ListField(child=serializers.IntegerField())
    created_at = serializers.DateTimeField()


class AssistantSessionOutput(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    title = serializers.CharField()
    message_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class AssistantSessionDetailOutput(serializers.Serializer[Any]):
    session = AssistantSessionOutput()
    messages = AssistantMessageOutput(many=True)


class LogFiltersInput(serializers.Serializer[Any]):
    sentiment = serializers.ChoiceField(choices=[item.value for item in Sentiment], required=False)
    topic = serializers.CharField(max_length=60, required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate_sentiment(self, value: str) -> Sentiment:
        return Sentiment(value)


class QuestionLogOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    session_id = serializers.UUIDField()
    user_id = serializers.IntegerField(allow_null=True)
    question = serializers.CharField()
    answer = serializers.CharField()
    sentiment = serializers.CharField(source="sentiment.value", allow_null=True, default=None)
    topic = serializers.CharField()
    products_count = serializers.IntegerField()
    input_tokens = serializers.IntegerField()
    output_tokens = serializers.IntegerField()
    cost = serializers.DecimalField(max_digits=12, decimal_places=6)
    latency_ms = serializers.IntegerField()
    error_code = serializers.CharField()
    created_at = serializers.DateTimeField()


class AssistantStatsOutput(serializers.Serializer[Any]):
    questions = serializers.IntegerField()
    sessions = serializers.IntegerField()
    input_tokens = serializers.IntegerField()
    output_tokens = serializers.IntegerField()
    cost = serializers.DecimalField(max_digits=12, decimal_places=6)
    average_latency_ms = serializers.IntegerField()
    sentiments = serializers.DictField(child=serializers.IntegerField())
    top_topics = serializers.ListField(child=serializers.ListField())
