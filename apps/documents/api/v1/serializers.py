from typing import Any

from rest_framework import serializers

from apps.analytics.domain.periods import Period
from apps.documents.domain.enums import JobFormat
from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.enums import SalesPeriod, SaleStatus
from core.api.fields import MAX_INTEGER


def choices(enum: type[Any]) -> list[str]:
    return [item.value for item in enum]


class FormatField(serializers.ChoiceField):
    def __init__(self, allowed: tuple[JobFormat, ...], **options: Any) -> None:
        super().__init__(choices=[item.value for item in allowed], **options)

    def to_internal_value(self, data: Any) -> JobFormat:
        return JobFormat(super().to_internal_value(data))


class SalesExportInput(serializers.Serializer[Any]):
    format = FormatField((JobFormat.CSV, JobFormat.XLSX, JobFormat.PDF))
    period = serializers.ChoiceField(choices=choices(SalesPeriod), required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    payment_method = serializers.ChoiceField(choices=choices(PaymentMethod), required=False)
    seller_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    product_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    status = serializers.ChoiceField(choices=choices(SaleStatus), required=False)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ProductsExportInput(serializers.Serializer[Any]):
    format = FormatField((JobFormat.CSV, JobFormat.XLSX))


class ProductsImportInput(serializers.Serializer[Any]):
    file = serializers.FileField()
    dry_run = serializers.BooleanField(default=False)


class AnalyticsReportInput(serializers.Serializer[Any]):
    period = serializers.ChoiceField(choices=choices(Period), required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    category_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    payment_method = serializers.ChoiceField(choices=choices(PaymentMethod), required=False)
    seller_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)


class JobOutput(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    kind = serializers.CharField(source="kind.value")
    format = serializers.CharField(source="format.value")
    status = serializers.CharField(source="status.value")
    filename = serializers.CharField()
    size = serializers.IntegerField()
    summary = serializers.JSONField()
    error = serializers.CharField()
    downloadable = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
