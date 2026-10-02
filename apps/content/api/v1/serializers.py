from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.catalog.api.v1.serializers import CategoryOutput, ProductCardOutput
from apps.content.domain.enums import ContactStatus, ContactSubject

PHONE_PATTERN = r"^\+?[\d\s().-]{7,20}$"


def choices(enum: type[Any]) -> list[str]:
    return [item.value for item in enum]


class ContactInput(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    phone = serializers.RegexField(PHONE_PATTERN, required=False, allow_blank=True, default="")
    subject = serializers.ChoiceField(choices=choices(ContactSubject))
    message = serializers.CharField(min_length=10, max_length=5000)
    website = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_subject(self, value: str) -> ContactSubject:
        return ContactSubject(value)


class HandleContactInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=choices(ContactStatus))
    note = serializers.CharField(max_length=2000, allow_blank=True)

    def validate_status(self, value: str) -> ContactStatus:
        return ContactStatus(value)


class ContactFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=choices(ContactStatus), required=False)
    subject = serializers.ChoiceField(choices=choices(ContactSubject), required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_status(self, value: str) -> ContactStatus:
        return ContactStatus(value)

    def validate_subject(self, value: str) -> ContactSubject:
        return ContactSubject(value)


class ContactMessageOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    subject = serializers.CharField(source="subject.value")
    message = serializers.CharField()
    status = serializers.CharField(source="status.value")
    note = serializers.CharField()
    user_id = serializers.IntegerField(allow_null=True)
    handled_by = serializers.CharField(allow_null=True)
    handled_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class SubscribeInput(serializers.Serializer[Any]):
    email = serializers.EmailField()
    source = serializers.CharField(  # type: ignore[assignment]
        max_length=40, required=False, allow_blank=True, default=""
    )


class UnsubscribeInput(serializers.Serializer[Any]):
    token = serializers.UUIDField()


class SubscriptionOutput(serializers.Serializer[Any]):
    email = serializers.EmailField()
    code = serializers.CharField()
    discount = serializers.IntegerField()
    already_subscribed = serializers.BooleanField()


class SubscriberFiltersInput(serializers.Serializer[Any]):
    active = serializers.BooleanField(required=False, allow_null=True, default=None)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)


class SubscriberOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    source = serializers.CharField()  # type: ignore[assignment]
    is_active = serializers.BooleanField()
    subscribed_at = serializers.DateTimeField()
    unsubscribed_at = serializers.DateTimeField(allow_null=True)


class PageFieldsInput(serializers.Serializer[Any]):
    slug = serializers.SlugField(max_length=80)
    title = serializers.CharField(max_length=160)
    summary = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    body = serializers.CharField()
    is_published = serializers.BooleanField(default=True)
    position = serializers.IntegerField(min_value=0, max_value=32767, default=0)


class PageSummaryOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    title = serializers.CharField()
    summary = serializers.CharField()
    is_published = serializers.BooleanField()
    position = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class PageOutput(PageSummaryOutput):
    body = serializers.CharField()


class FaqFieldsInput(serializers.Serializer[Any]):
    question = serializers.CharField(max_length=255)
    answer = serializers.CharField()
    category = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    position = serializers.IntegerField(min_value=0, max_value=32767, default=0)
    is_published = serializers.BooleanField(default=True)


class FaqOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    question = serializers.CharField()
    answer = serializers.CharField()
    category = serializers.CharField()
    position = serializers.IntegerField()
    is_published = serializers.BooleanField()


class FaqGroupOutput(serializers.Serializer[Any]):
    category = serializers.CharField()
    entries = FaqOutput(many=True)


class BannerFieldsInput(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=120)
    subtitle = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    image = serializers.URLField(max_length=500)
    link_url = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    link_label = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    position = serializers.IntegerField(min_value=0, max_value=32767, default=0)
    is_active = serializers.BooleanField(default=True)
    starts_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class BannerOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    image = serializers.URLField()
    link_url = serializers.CharField()
    link_label = serializers.CharField()
    position = serializers.IntegerField()
    is_active = serializers.BooleanField()
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)


class OpeningHoursInput(serializers.Serializer[Any]):
    days = serializers.CharField(max_length=40)
    hours = serializers.CharField(max_length=40)


class SettingsInput(serializers.Serializer[Any]):
    usd_to_cdf = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1"))
    hotline = serializers.CharField(max_length=30, allow_blank=True)
    whatsapp = serializers.CharField(max_length=30, allow_blank=True)
    email = serializers.EmailField(allow_blank=True)
    address = serializers.CharField(max_length=255, allow_blank=True)
    opening_hours = OpeningHoursInput(many=True)
    payment_methods = serializers.ListField(child=serializers.CharField(max_length=16))
    social_links = serializers.DictField(child=serializers.URLField(max_length=300))
    newsletter_code = serializers.CharField(max_length=30, allow_blank=True)
    newsletter_discount = serializers.IntegerField(min_value=0, max_value=90)

    def validate_opening_hours(self, value: list[dict[str, str]]) -> list[dict[str, str]]:
        return [dict(item) for item in value]


class ShippingOutput(serializers.Serializer[Any]):
    free_threshold = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    flat_fee = serializers.DecimalField(max_digits=10, decimal_places=2)


class PublicSettingsOutput(serializers.Serializer[Any]):
    usd_to_cdf = serializers.DecimalField(max_digits=10, decimal_places=2)
    hotline = serializers.CharField()
    whatsapp = serializers.CharField()
    whatsapp_url = serializers.CharField()
    email = serializers.CharField()
    address = serializers.CharField()
    opening_hours = serializers.ListField(child=serializers.DictField())
    payment_methods = serializers.ListField(child=serializers.CharField())
    social_links = serializers.DictField(child=serializers.CharField())
    newsletter_discount = serializers.IntegerField()
    shipping = ShippingOutput()


class AdminSettingsOutput(PublicSettingsOutput):
    newsletter_code = serializers.CharField()


class CategoryBlockOutput(serializers.Serializer[Any]):
    category = CategoryOutput()
    products = ProductCardOutput(many=True)


class HomeOutput(serializers.Serializer[Any]):
    banners = BannerOutput(many=True)
    deals = ProductCardOutput(many=True)
    new_arrivals = ProductCardOutput(many=True)
    best_sellers = ProductCardOutput(many=True)
    categories = CategoryBlockOutput(many=True)
