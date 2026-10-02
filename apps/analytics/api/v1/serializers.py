from datetime import date
from typing import Any

from rest_framework import serializers

from apps.analytics.domain.periods import Period
from apps.orders.domain.enums import PaymentMethod

RANKINGS = ("revenue", "units", "profit")
EARLIEST_DATE = date(2000, 1, 1)
LATEST_DATE = date(2100, 12, 31)


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=14, decimal_places=2, **options)


class AnalyticsFiltersInput(serializers.Serializer[Any]):
    period = serializers.ChoiceField(choices=[item.value for item in Period], required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    category_id = serializers.IntegerField(min_value=1, required=False)
    payment_method = serializers.ChoiceField(
        choices=[item.value for item in PaymentMethod], required=False
    )
    seller_id = serializers.IntegerField(min_value=1, required=False)

    def validate_period(self, value: str) -> Period:
        return Period(value)

    def validate_payment_method(self, value: str) -> PaymentMethod:
        return PaymentMethod(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = attrs.get("date_from"), attrs.get("date_to")
        for name in ("date_from", "date_to"):
            day = attrs.get(name)
            if day is not None and not EARLIEST_DATE <= day <= LATEST_DATE:
                raise serializers.ValidationError({name: ["Date hors de la période autorisée."]})
        if start and end and start > end:
            raise serializers.ValidationError({"date_to": ["Doit suivre la date de début."]})
        return attrs


class RankingInput(serializers.Serializer[Any]):
    by = serializers.ChoiceField(choices=RANKINGS, default="revenue")
    limit = serializers.IntegerField(min_value=1, max_value=50, required=False)


class MetricOutput(serializers.Serializer[Any]):
    value = money()
    previous = money()
    change = serializers.FloatField(allow_null=True)


class SummaryOutput(serializers.Serializer[Any]):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    revenue = MetricOutput()
    profit = MetricOutput()
    sales_count = MetricOutput()
    units = MetricOutput()
    average_basket = MetricOutput()
    margin_rate = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    today_revenue = money()
    open_orders = serializers.IntegerField()


class SeriesPointOutput(serializers.Serializer[Any]):
    bucket = serializers.DateField()
    revenue = money()
    profit = money()
    sales_count = serializers.IntegerField()
    average_basket = money()


class SeriesOutput(serializers.Serializer[Any]):
    granularity = serializers.CharField(source="granularity.value")
    points = SeriesPointOutput(many=True)


class PaymentShareOutput(serializers.Serializer[Any]):
    payment_method = serializers.CharField()
    revenue = money()
    sales_count = serializers.IntegerField()
    share = serializers.FloatField()


class CategoryPerformanceOutput(serializers.Serializer[Any]):
    category_id = serializers.IntegerField()
    name = serializers.CharField()
    revenue = money()
    profit = money()
    units = serializers.IntegerField()
    margin_rate = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    share = serializers.FloatField()


class ProductPerformanceOutput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField()
    name = serializers.CharField()
    image = serializers.CharField()
    revenue = money()
    profit = money()
    units = serializers.IntegerField()


class HeatCellOutput(serializers.Serializer[Any]):
    weekday = serializers.IntegerField()
    hour = serializers.IntegerField()
    sales_count = serializers.IntegerField()
    revenue = money()


class SellerRankingOutput(serializers.Serializer[Any]):
    seller_id = serializers.IntegerField()
    name = serializers.CharField()
    revenue = money()
    profit = money()
    sales_count = serializers.IntegerField()
    units = serializers.IntegerField()
    share = serializers.FloatField()


class SlowMoverOutput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField()
    name = serializers.CharField()
    image = serializers.CharField()
    stock = serializers.IntegerField()
    last_sold_at = serializers.DateTimeField(allow_null=True)


class RecentSaleOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    product_name = serializers.CharField()
    product_image = serializers.CharField()
    quantity = serializers.IntegerField()
    total = money()
    payment_method = serializers.CharField(source="payment_method.value")
    status = serializers.CharField(source="status.value")
    seller_name = serializers.CharField(source="seller.name")
    sold_to = serializers.CharField()
    sold_at = serializers.DateTimeField()


class OpenOrderOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    number = serializers.CharField()
    status = serializers.CharField(source="status.value")
    created_at = serializers.DateTimeField()
    total = money()
    items_count = serializers.IntegerField()
    client_name = serializers.CharField()
    reseller_name = serializers.CharField(allow_null=True)


class OpenOrdersOutput(serializers.Serializer[Any]):
    count = serializers.IntegerField()
    results = OpenOrderOutput(many=True)
