from decimal import Decimal
from typing import Any

from django_stubs_ext import StrPromise
from rest_framework import serializers

from apps.orders.conf import order_settings
from apps.orders.domain.commands import DeliveryAddress, OrderLineInput
from apps.orders.domain.enums import (
    CLIENT_CANCEL_REASONS,
    AttemptReason,
    CancelReason,
    OrderStatus,
    PaymentMethod,
)
from core.api.fields import MAX_INTEGER

PHONE_PATTERN = r"^\+?[\d\s().-]{7,20}$"
PHONE_ERROR: dict[str, str | StrPromise] = {"invalid": "Numéro de téléphone invalide."}
HANDOVER_STATUSES = frozenset({OrderStatus.CONFIRMED, OrderStatus.PAID, OrderStatus.SHIPPING})
TRANSITION_TARGETS = [
    status.value
    for status in OrderStatus
    if status not in (OrderStatus.PENDING, OrderStatus.ASSIGNED)
]


class OrderLineInputSerializer(serializers.Serializer[Any]):
    product_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    variant_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)

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
    # how many points the client wants to use (1 point = $1), up to their balance and the items
    points = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal(0), required=False, default=Decimal(0)
    )
    # store credit (avoir, in dollars) the client wants to use, up to their balance and the total
    store_credit = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal(0), required=False, default=Decimal(0)
    )
    pickup = serializers.BooleanField(required=False, default=False)


class AssignableSearchInput(serializers.Serializer[Any]):
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)


class CouponCodeInput(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=40)


class CartContextInput(serializers.Serializer[Any]):
    city = serializers.CharField(max_length=120, required=False, allow_blank=True)


class PlaceOrderInput(QuoteInput):
    coupon_code = serializers.CharField(
        max_length=40, required=False, allow_blank=True, allow_null=True, default=None
    )
    payment_method = serializers.ChoiceField(choices=[item.value for item in PaymentMethod])
    address_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    address = DeliveryAddressInput(required=False, allow_null=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    points = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal(0), required=False, default=Decimal(0)
    )
    # store credit (avoir, in dollars) the client wants to use, up to their balance and the total
    store_credit = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal(0), required=False, default=Decimal(0)
    )
    pickup = serializers.BooleanField(required=False, default=False)

    def validate_payment_method(self, value: str) -> PaymentMethod:
        return PaymentMethod(value)


class CartItemInput(OrderLineInputSerializer):
    pass


class CartQuantityInput(serializers.Serializer[Any]):
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)


class CartMergeInput(serializers.Serializer[Any]):
    token = serializers.UUIDField()


class CancelInput(serializers.Serializer[Any]):
    reason = serializers.ChoiceField(choices=[item.value for item in CLIENT_CANCEL_REASONS])
    details = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_reason(self, value: str) -> CancelReason:
        return CancelReason(value)


class RecordAttemptInput(serializers.Serializer[Any]):
    reason = serializers.ChoiceField(choices=[item.value for item in AttemptReason])
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")

    def validate_reason(self, value: str) -> AttemptReason:
        return AttemptReason(value)


class RecordSerialsInput(serializers.Serializer[Any]):
    # the whole list for the line: numbers left out are removed
    serials = serializers.ListField(
        child=serializers.CharField(max_length=60, allow_blank=True), max_length=100
    )

    def validate_serials(self, value: list[str]) -> tuple[str, ...]:
        return tuple(value)


class AttemptOutput(serializers.Serializer[Any]):
    at = serializers.DateTimeField()
    reason = serializers.CharField()
    reason_label = serializers.CharField()
    note = serializers.CharField()


class RateResellerInput(serializers.Serializer[Any]):
    score = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class RatingOutput(serializers.Serializer[Any]):
    score = serializers.IntegerField()
    comment = serializers.CharField()
    created_at = serializers.DateTimeField()


class RecordRefundInput(serializers.Serializer[Any]):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class TrackInput(serializers.Serializer[Any]):
    number = serializers.CharField(max_length=20)
    contact = serializers.CharField(max_length=254)


class AssignInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DeclineInput(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ReturnLineInput(serializers.Serializer[Any]):
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class TransitionInput(serializers.Serializer[Any]):
    to = serializers.ChoiceField(choices=TRANSITION_TARGETS)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    delivery_code = serializers.RegexField(
        r"^\s*\d{6}\s*$",
        required=False,
        allow_blank=True,
        default="",
        error_messages={"invalid": "Le code de livraison compte 6 chiffres."},
    )

    def validate_to(self, value: str) -> OrderStatus:
        return OrderStatus(value)


class OrderFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[*[item.value for item in OrderStatus], "unassigned", "refund_pending"],
        required=False,
    )
    reseller_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
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
        elif status == "refund_pending":
            attrs["refund_pending"] = True
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
    points = serializers.DecimalField(max_digits=10, decimal_places=2)
    points_available = serializers.DecimalField(max_digits=10, decimal_places=2)
    store_credit = serializers.DecimalField(max_digits=10, decimal_places=2)
    store_credit_available = serializers.DecimalField(max_digits=10, decimal_places=2)
    delivery_method = serializers.CharField()
    pickup_address = serializers.CharField()
    shipping_quote_required = serializers.BooleanField()
    pickup_available = serializers.BooleanField()
    campaign_id = serializers.IntegerField(allow_null=True)
    campaign_name = serializers.CharField()
    campaign_kind = serializers.CharField()
    campaign_percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    campaign_discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    campaign_advantage = serializers.DecimalField(max_digits=10, decimal_places=2)


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
    # "due" until staff record the refund of a paid order that was cancelled, then "done"
    refund_status = serializers.CharField(allow_null=True)


class SuggestedResellerOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    # "invited_client": the active reseller who invited the client, whenever that was
    reason = serializers.CharField()
    invited_at = serializers.DateTimeField(allow_null=True)


# back-office list: staff who can assign also get the reseller who invited the client
class BackofficeOrderSummaryOutput(OrderSummaryOutput):
    suggested_reseller = SuggestedResellerOutput(allow_null=True)


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
    # the line's share of the order's coupon and points, and the real money paid for it
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    points = serializers.DecimalField(max_digits=10, decimal_places=2)
    credit = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    # units given back after delivery and the real money owed back for them
    returned_quantity = serializers.IntegerField()
    returned_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    # each unit's serial number or IMEI, when the product needs one
    serial_required = serializers.BooleanField()
    serials = serializers.ListField(child=serializers.CharField())


class StatusEntryOutput(serializers.Serializer[Any]):
    status = serializers.CharField()
    at = serializers.DateTimeField()
    actor_role = serializers.CharField()
    actor_name = serializers.CharField(allow_null=True)
    note = serializers.CharField()


class PersonOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
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
    summary_output: type[OrderSummaryOutput] = BackofficeOrderSummaryOutput

    items = OrderLineOutput(many=True)
    address = DeliveryAddressOutput()
    payment_method = serializers.CharField()
    note = serializers.CharField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    coupon_code = serializers.CharField()
    shipping_zone = serializers.CharField()
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    delivery_method = serializers.CharField()
    pickup_address = serializers.CharField()
    delivery_estimate = serializers.CharField()
    awaiting_shipping_quote = serializers.BooleanField()
    points = serializers.DecimalField(max_digits=10, decimal_places=2)
    store_credit = serializers.DecimalField(max_digits=10, decimal_places=2)
    campaign_name = serializers.CharField()
    campaign_discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    points_earned = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    cancel_reason = serializers.CharField()
    refund_due = serializers.DecimalField(max_digits=10, decimal_places=2)
    refunded_at = serializers.DateTimeField(allow_null=True)
    refund_note = serializers.CharField()
    delivery_code_attempts = serializers.IntegerField()
    delivery_code_locked = serializers.BooleanField()
    rating = RatingOutput(allow_null=True)
    can_rate = serializers.BooleanField()
    delivery_attempts = AttemptOutput(many=True)
    history = StatusEntryOutput(many=True)
    allowed_transitions = serializers.ListField(child=serializers.CharField())
    client = PersonOutput()
    reseller = PersonOutput(allow_null=True)
    conversation_id = serializers.IntegerField(allow_null=True)
    # true for the assigned reseller 7 days after delivery, or once the order is cancelled: the
    # client's phone, street, quarter and delivery note then come back empty
    contact_hidden = serializers.BooleanField()

    def to_representation(self, instance: Any) -> dict[str, Any]:
        return {**self.summary_output(instance.summary).data, **super().to_representation(instance)}


class ClientOrderDetailOutput(OrderDetailOutput):
    summary_output = OrderSummaryOutput

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)
        data.pop("client", None)
        data.pop("contact_hidden", None)
        # the client's own code, to give the reseller at handover, until the order is delivered
        data["delivery_code"] = (
            instance.delivery_code if instance.summary.status in HANDOVER_STATUSES else None
        )
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
    # cash to remit first (over the cap or past 24 hours): new orders are refused until then
    cash_blocked = serializers.CharField(allow_null=True)
    # suspended (reseller policy, section 10): no new orders until then
    suspended_until = serializers.DateTimeField(allow_null=True)
