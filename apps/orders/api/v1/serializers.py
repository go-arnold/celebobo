from typing import Any

from django_stubs_ext import StrPromise
from rest_framework import serializers

from apps.orders.conf import order_settings
from apps.orders.domain.commands import DeliveryAddress, OrderLineInput
from apps.orders.domain.enums import CancelReason, OrderStatus, PaymentMethod

PHONE_PATTERN = r"^\+?[\d\s().-]{7,20}$"
PHONE_ERROR: dict[str, str | StrPromise] = {"invalid": "Numéro de téléphone invalide."}
TRANSITION_TARGETS = [
    status.value
    for status in OrderStatus
    if status not in (OrderStatus.PENDING, OrderStatus.ASSIGNED)
]


class OrderLineInputSerializer(serializers.Serializer[Any]):
    product_id = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)

    def validate_quantity(self, value: int) -> int:
        limit = order_settings().max_quantity
        if value > limit:
            raise serializers.ValidationError(f"{limit} unités maximum par article.")
        return value

    def validate(self, attrs: dict[str, Any]) -> OrderLineInput:
        return OrderLineInput(**attrs)


class DeliveryAddressInput(serializers.Serializer[Any]):
    recipient = serializers.CharField(max_length=120)
    phone = serializers.RegexField(PHONE_PATTERN, error_messages=PHONE_ERROR)
    line1 = serializers.CharField(max_length=255)
    quarter = serializers.CharField(max_length=120)
    city = serializers.CharField(max_length=120)
    country = serializers.CharField(max_length=80)

    def validate(self, attrs: dict[str, Any]) -> DeliveryAddress:
        return DeliveryAddress(**attrs)


class QuoteInput(serializers.Serializer[Any]):
    lines = OrderLineInputSerializer(many=True, allow_empty=False)

    def validate_lines(self, value: list[OrderLineInput]) -> tuple[OrderLineInput, ...]:
        return tuple(value)


class QuoteRequestInput(QuoteInput):
    city = serializers.CharField(max_length=120, required=False, allow_blank=True)
    coupon_code = serializers.CharField(max_length=40, required=False, allow_blank=True)


class CouponCodeInput(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=40)


class CartContextInput(serializers.Serializer[Any]):
    city = serializers.CharField(max_length=120, required=False, allow_blank=True)


class PlaceOrderInput(QuoteInput):
    coupon_code = serializers.CharField(
        max_length=40, required=False, allow_blank=True, allow_null=True, default=None
    )
    payment_method = serializers.ChoiceField(choices=[item.value for item in PaymentMethod])
    address_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    address = DeliveryAddressInput(required=False, allow_null=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate_payment_method(self, value: str) -> PaymentMethod:
        return PaymentMethod(value)


class CartItemInput(OrderLineInputSerializer):
    pass


class CartQuantityInput(serializers.Serializer[Any]):
    quantity = serializers.IntegerField(min_value=1)


class CartMergeInput(serializers.Serializer[Any]):
    token = serializers.UUIDField()


class CancelInput(serializers.Serializer[Any]):
    reason = serializers.ChoiceField(choices=[item.value for item in CancelReason])
    details = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_reason(self, value: str) -> CancelReason:
        return CancelReason(value)


class TrackInput(serializers.Serializer[Any]):
    number = serializers.CharField(max_length=20)
    contact = serializers.CharField(max_length=254)


class AssignInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DeclineInput(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class TransitionInput(serializers.Serializer[Any]):
    to = serializers.ChoiceField(choices=TRANSITION_TARGETS)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_to(self, value: str) -> OrderStatus:
        return OrderStatus(value)


class OrderFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[*[item.value for item in OrderStatus], "unassigned"], required=False
    )
    reseller_id = serializers.IntegerField(min_value=1, required=False)
    payment_method = serializers.ChoiceField(
        choices=[item.value for item in PaymentMethod], required=False
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    search = serializers.CharField(max_length=100, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        status = attrs.pop("status", None)
        if status == "unassigned":
            attrs["unassigned"] = True
        elif status:
            attrs["status"] = OrderStatus(status)
        if "payment_method" in attrs:
            attrs["payment_method"] = PaymentMethod(attrs["payment_method"])
        return attrs


class ClientStatusInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=[item.value for item in OrderStatus], required=False)


class QuoteLineOutput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    variant_label = serializers.CharField()
    image = serializers.CharField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    quantity = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class QuoteOutput(serializers.Serializer[Any]):
    lines = QuoteLineOutput(many=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    free_shipping_remaining = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    shipping_zone = serializers.CharField()
    delivery_estimate = serializers.CharField()
    coupon_code = serializers.CharField(allow_null=True)
    coupon_error = serializers.CharField(allow_null=True)


class CartLineOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(allow_null=True)
    quantity = serializers.IntegerField()
    available = serializers.BooleanField()


class CartOutput(serializers.Serializer[Any]):
    token = serializers.CharField(allow_null=True)
    lines = CartLineOutput(many=True)
    quote = QuoteOutput()


class OrderSummaryOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    number = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    items_count = serializers.IntegerField()
    preview_name = serializers.CharField()
    preview_image = serializers.CharField()
    client_name = serializers.CharField()
    reseller_name = serializers.CharField(allow_null=True)


class OrderLineOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    product_id = serializers.IntegerField(allow_null=True)
    variant_id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    variant_label = serializers.CharField()
    image = serializers.CharField()
    sku = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class StatusEntryOutput(serializers.Serializer[Any]):
    status = serializers.CharField()
    at = serializers.DateTimeField()
    actor_role = serializers.CharField()
    actor_name = serializers.CharField(allow_null=True)
    note = serializers.CharField()


class PersonOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(allow_null=True)
    availability = serializers.CharField(allow_null=True)


class DeliveryAddressOutput(serializers.Serializer[Any]):
    recipient = serializers.CharField()
    phone = serializers.CharField()
    line1 = serializers.CharField()
    quarter = serializers.CharField()
    city = serializers.CharField()
    country = serializers.CharField()


class OrderDetailOutput(serializers.Serializer[Any]):
    items = OrderLineOutput(many=True)
    address = DeliveryAddressOutput()
    payment_method = serializers.CharField()
    note = serializers.CharField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    coupon_code = serializers.CharField()
    shipping_zone = serializers.CharField()
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    cancel_reason = serializers.CharField()
    history = StatusEntryOutput(many=True)
    allowed_transitions = serializers.ListField(child=serializers.CharField())
    client = PersonOutput()
    reseller = PersonOutput(allow_null=True)
    conversation_id = serializers.IntegerField(allow_null=True)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        return {**OrderSummaryOutput(instance.summary).data, **super().to_representation(instance)}


class ClientOrderDetailOutput(OrderDetailOutput):
    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)
        data.pop("client", None)
        if data.get("reseller"):
            data["reseller"] = {
                key: data["reseller"][key] for key in ("id", "name", "availability")
            }
        return data


class TrackedItemOutput(serializers.Serializer[Any]):
    name = serializers.CharField()
    variant_label = serializers.CharField()
    quantity = serializers.IntegerField()


class TrackedStatusOutput(serializers.Serializer[Any]):
    status = serializers.CharField()
    at = serializers.DateTimeField()


class TrackingOutput(serializers.Serializer[Any]):
    number = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    items = TrackedItemOutput(many=True)
    history = TrackedStatusOutput(many=True)


class AssignableResellerOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    availability = serializers.CharField()
    open_orders = serializers.IntegerField()
