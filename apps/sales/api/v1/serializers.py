from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.commands import ConversionLine, RecordSale
from apps.sales.domain.enums import RefundKind, SalesPeriod, SaleStatus
from core.api.fields import MAX_INTEGER

MAX_BULK_LINES = 50


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=12, decimal_places=2, **options)


def choices(enum: type[Any]) -> list[str]:
    return [item.value for item in enum]


class PaymentMethodField(serializers.ChoiceField):
    def __init__(self, **options: Any) -> None:
        super().__init__(choices=choices(PaymentMethod), **options)

    def to_internal_value(self, data: Any) -> PaymentMethod:
        return PaymentMethod(super().to_internal_value(data))


class RecordSaleInput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    variant_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    quantity = serializers.IntegerField(min_value=1, max_value=10_000)
    unit_price = money(min_value=Decimal("0.01"))
    payment_method = PaymentMethodField()
    sold_at = serializers.DateTimeField(required=False, allow_null=True)
    sold_to = serializers.CharField(max_length=160, required=False, allow_blank=True)
    buyer_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    seller_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )


class RecordSaleLine(RecordSaleInput):
    def validate(self, attrs: dict[str, Any]) -> RecordSale:
        return RecordSale(**attrs)


class BulkSalesInput(serializers.Serializer[Any]):
    lines = RecordSaleLine(many=True, allow_empty=False)

    def validate_lines(self, value: list[RecordSale]) -> list[RecordSale]:
        if len(value) > MAX_BULK_LINES:
            raise serializers.ValidationError(f"{MAX_BULK_LINES} lignes maximum.")
        return value


class EditSaleInput(serializers.Serializer[Any]):
    unit_price = money(min_value=Decimal("0.01"))
    payment_method = PaymentMethodField()
    sold_at = serializers.DateTimeField()
    sold_to = serializers.CharField(max_length=160, allow_blank=True)


class RefundSaleInput(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=choices(RefundKind))
    amount = money(min_value=Decimal("0.01"), required=False, allow_null=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_kind(self, value: str) -> RefundKind:
        return RefundKind(value)


class SaleFiltersInput(serializers.Serializer[Any]):
    period = serializers.ChoiceField(choices=choices(SalesPeriod), required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    payment_method = PaymentMethodField(required=False)
    seller_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    product_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    status = serializers.ChoiceField(choices=choices(SaleStatus), required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_period(self, value: str) -> SalesPeriod:
        return SalesPeriod(value)

    def validate_status(self, value: str) -> SaleStatus:
        return SaleStatus(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end and start > end:
            raise serializers.ValidationError({"date_to": ["Doit suivre la date de début."]})
        return attrs


class ConversionLineInput(serializers.Serializer[Any]):
    item_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    unit_price = money(min_value=Decimal("0.01"))

    def validate(self, attrs: dict[str, Any]) -> ConversionLine:
        return ConversionLine(**attrs)


class ConvertOrderInput(serializers.Serializer[Any]):
    payment_method = PaymentMethodField(required=False, allow_null=True)
    sold_at = serializers.DateTimeField(required=False, allow_null=True)
    sold_to = serializers.CharField(max_length=160, required=False, allow_blank=True)
    lines = ConversionLineInput(many=True, required=False)

    def validate_lines(self, value: list[ConversionLine]) -> tuple[ConversionLine, ...]:
        if len({line.item_id for line in value}) != len(value):
            raise serializers.ValidationError("Article en double.")
        return tuple(value)


class ConvertibleSearchInput(serializers.Serializer[Any]):
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ResellerScopeInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)


class RecordPayoutInput(serializers.Serializer[Any]):
    reseller_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    amount = money(min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class SalePersonOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()


class RefundOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    kind = serializers.CharField(source="kind.value")
    amount = money()
    reason = serializers.CharField()
    by = SalePersonOutput(allow_null=True)
    created_at = serializers.DateTimeField()


class SaleOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(allow_null=True)
    product_name = serializers.CharField()
    variant_label = serializers.CharField()
    product_image = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = money()
    unit_cost = money(allow_null=True)
    total = money()
    refunded_amount = money()
    profit = money(allow_null=True)
    payment_method = serializers.CharField(source="payment_method.value")
    status = serializers.CharField(source="status.value")
    sold_to = serializers.CharField()
    buyer = SalePersonOutput(allow_null=True)
    seller = SalePersonOutput()
    order_id = serializers.IntegerField(allow_null=True)
    order_number = serializers.CharField(allow_null=True)
    sold_at = serializers.DateTimeField()
    recorded_at = serializers.DateTimeField()


class SaleDetailOutput(SaleOutput):
    refunds = RefundOutput(many=True)


class SalesStatsOutput(serializers.Serializer[Any]):
    revenue = money()
    profit = money()
    count = serializers.IntegerField()
    units = serializers.IntegerField()
    average = money()


class ConvertibleOrderOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    number = serializers.CharField()
    status = serializers.CharField()
    client_name = serializers.CharField()
    total = money()
    created_at = serializers.DateTimeField()
    convertible = serializers.BooleanField()
    blocked_reason = serializers.CharField(allow_null=True)
    items_count = serializers.IntegerField()


class CommissionEntryOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    kind = serializers.CharField(source="kind.value")
    sale_id = serializers.IntegerField(allow_null=True)
    rate = serializers.DecimalField(max_digits=4, decimal_places=3)
    base_amount = money()
    amount = money()
    created_at = serializers.DateTimeField()


class CommissionSummaryOutput(serializers.Serializer[Any]):
    reseller = SalePersonOutput()
    rate = serializers.DecimalField(max_digits=4, decimal_places=3)
    earned_this_month = money()
    earned_total = money()
    paid_total = money()
    due = money()


class MonthlyCommissionOutput(serializers.Serializer[Any]):
    month = serializers.CharField()
    earned = money()
    paid = money()


class PayoutOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    reseller = SalePersonOutput()
    amount = money()
    note = serializers.CharField()
    paid_at = serializers.DateTimeField()
    paid_by = SalePersonOutput(allow_null=True)
