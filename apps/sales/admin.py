from django.contrib import admin
from import_export.admin import ExportMixin

from apps.sales.models import (
    CommissionEntry,
    DeliveryCredit,
    Payout,
    PayoutStatement,
    Refund,
    Sale,
)


class RefundInline(admin.TabularInline[Refund, Sale]):
    model = Refund
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "amount", "reason", "by", "created_at")


@admin.register(Sale)
class SaleAdmin(ExportMixin, admin.ModelAdmin[Sale]):
    list_display = ("product_name", "quantity", "unit_price", "seller", "status", "sold_at")
    list_filter = ("status", "payment_method")
    search_fields = ("product_name", "sold_to")
    raw_id_fields = ("product", "variant", "seller", "buyer", "order", "order_item", "recorded_by")
    inlines = (RefundInline,)

    def has_change_permission(self, request: object, obj: Sale | None = None) -> bool:
        return False


@admin.register(CommissionEntry)
class CommissionEntryAdmin(admin.ModelAdmin[CommissionEntry]):
    list_display = ("reseller", "kind", "amount", "rule", "sale", "available_at", "statement")
    list_filter = ("kind", "rule")
    raw_id_fields = ("reseller", "sale", "statement")

    def has_change_permission(self, request: object, obj: CommissionEntry | None = None) -> bool:
        return False


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin[Payout]):
    list_display = ("reseller", "amount", "paid_at", "paid_by")
    raw_id_fields = ("reseller", "paid_by")


@admin.register(PayoutStatement)
class PayoutStatementAdmin(admin.ModelAdmin[PayoutStatement]):
    list_display = ("reseller", "payout_date", "status", "commissions", "delivery_fees", "total")
    list_filter = ("status", "payout_date")
    raw_id_fields = ("reseller", "payout")

    def has_change_permission(self, request: object, obj: PayoutStatement | None = None) -> bool:
        return False


@admin.register(DeliveryCredit)
class DeliveryCreditAdmin(admin.ModelAdmin[DeliveryCredit]):
    list_display = ("reseller", "order_number", "kind", "amount", "available_at", "statement")
    list_filter = ("kind",)
    raw_id_fields = ("reseller", "order", "statement")

    def has_change_permission(self, request: object, obj: DeliveryCredit | None = None) -> bool:
        return False
