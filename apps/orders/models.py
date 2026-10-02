import uuid

from django.conf import settings
from django.db import models

from apps.orders.domain.enums import CancelReason, OrderStatus, PaymentMethod

STATUS_CHOICES = [(item.value, item.label) for item in OrderStatus]
PAYMENT_CHOICES = [(item.value, item.label) for item in PaymentMethod]
CANCEL_CHOICES = [(item.value, item.value) for item in CancelReason]
MONEY_DIGITS = 10
MONEY_PLACES = 2


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "panier"
        verbose_name_plural = "paniers"

    def __str__(self) -> str:
        return f"Panier {self.token}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    variant = models.ForeignKey(
        "catalog.ProductVariant", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    quantity = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("cart", "product", "variant"),
                name="orders_cart_item_unique",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="orders_cart_item_quantity_positive"
            ),
        )

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_id}"


class Order(models.Model):
    number = models.CharField(max_length=16, unique=True)
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=OrderStatus.PENDING.value
    )
    assigned_reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_orders",
    )
    recipient = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    line1 = models.CharField(max_length=255)
    quarter = models.CharField(max_length=120)
    city = models.CharField(max_length=120)
    country = models.CharField(max_length=80)
    payment_method = models.CharField(max_length=16, choices=PAYMENT_CHOICES)
    note = models.TextField(blank=True, max_length=1000)
    subtotal = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    shipping_fee = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    total = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    cancel_reason = models.CharField(max_length=24, choices=CANCEL_CHOICES, blank=True)
    cancel_details = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "commande"
        verbose_name_plural = "commandes"
        ordering = ("-created_at", "-pk")
        indexes = (
            models.Index(fields=("client", "-created_at"), name="orders_order_client"),
            models.Index(fields=("status", "-created_at"), name="orders_order_status"),
            models.Index(fields=("assigned_reseller", "status"), name="orders_order_reseller"),
        )
        constraints = (
            models.CheckConstraint(
                condition=models.Q(total=models.F("subtotal") + models.F("shipping_fee")),
                name="orders_order_total_consistent",
            ),
        )

    def __str__(self) -> str:
        return self.number

    @property
    def order_status(self) -> OrderStatus:
        return OrderStatus(self.status)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    product_name = models.CharField(max_length=255)
    variant_label = models.CharField(max_length=255, blank=True)
    product_image = models.URLField(max_length=500, blank=True)
    sku = models.CharField(max_length=64)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    list_unit_price = models.DecimalField(max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)

    class Meta:
        ordering = ("pk",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="orders_item_quantity_positive"
            ),
        )

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_name}"


class OrderStatusEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=12, choices=STATUS_CHOICES, blank=True)
    to_status = models.CharField(max_length=12, choices=STATUS_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_role = models.CharField(max_length=16)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self) -> str:
        return f"{self.order} → {self.to_status}"
