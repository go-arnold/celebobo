from django.contrib import admin

from apps.orders.models import Order, OrderItem, OrderStatusEvent


class OrderItemInline(admin.TabularInline[OrderItem, Order]):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "variant",
        "product_name",
        "variant_label",
        "sku",
        "quantity",
        "unit_price",
        "list_unit_price",
    )


class OrderStatusEventInline(admin.TabularInline[OrderStatusEvent, Order]):
    model = OrderStatusEvent
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "actor", "actor_role", "note", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin[Order]):
    list_display = ("number", "client", "status", "assigned_reseller", "total", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("number", "client__email", "recipient", "phone")
    raw_id_fields = ("client", "assigned_reseller")
    readonly_fields = ("number", "subtotal", "shipping_fee", "total", "created_at", "updated_at")
    inlines = (OrderItemInline, OrderStatusEventInline)

    def has_change_permission(self, request: object, obj: Order | None = None) -> bool:
        return False
