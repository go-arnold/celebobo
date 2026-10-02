from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.enums import CommissionKind, RefundKind, SaleStatus

PAYMENT_CHOICES = [(item.value, item.label) for item in PaymentMethod]
STATUS_CHOICES = [(item.value, item.value) for item in SaleStatus]
REFUND_CHOICES = [(item.value, item.value) for item in RefundKind]
COMMISSION_CHOICES = [(item.value, item.value) for item in CommissionKind]
DIGITS = 10
PLACES = 2


class Sale(models.Model):
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
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
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales"
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchases",
    )
    sold_to = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    unit_cost = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES, null=True, blank=True)
    refunded_amount = models.DecimalField(
        max_digits=DIGITS, decimal_places=PLACES, default=Decimal(0)
    )
    payment_method = models.CharField(max_length=16, choices=PAYMENT_CHOICES)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=SaleStatus.VALID.value, db_index=True
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    order_item = models.OneToOneField(
        "orders.OrderItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sale",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    sold_at = models.DateTimeField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vente"
        verbose_name_plural = "ventes"
        ordering = ("-sold_at", "-pk")
        indexes = (
            models.Index(fields=("seller", "-sold_at"), name="sales_sale_seller"),
            models.Index(fields=("product", "-sold_at"), name="sales_sale_product"),
        )
        constraints = (
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="sales_sale_quantity_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0), name="sales_sale_price_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(refunded_amount__gte=0)
                & models.Q(refunded_amount__lte=models.F("unit_price") * models.F("quantity")),
                name="sales_sale_refund_within_total",
            ),
        )

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_name}"

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def sale_status(self) -> SaleStatus:
        return SaleStatus(self.status)


class Refund(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="refunds")
    kind = models.CharField(max_length=8, choices=REFUND_CHOICES)
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    reason = models.CharField(max_length=500, blank=True)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self) -> str:
        return f"{self.kind} {self.amount}"


class CommissionEntry(models.Model):
    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="commission_entries"
    )
    sale = models.ForeignKey(
        Sale, null=True, blank=True, on_delete=models.SET_NULL, related_name="commissions"
    )
    kind = models.CharField(max_length=10, choices=COMMISSION_CHOICES)
    rate = models.DecimalField(max_digits=4, decimal_places=3)
    base_amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "écriture de commission"
        verbose_name_plural = "écritures de commission"
        ordering = ("-created_at", "-pk")
        indexes = (
            models.Index(fields=("reseller", "-created_at"), name="sales_commission_reseller"),
        )

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.amount:+}"


class Payout(models.Model):
    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts"
    )
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    note = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField()
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "paiement de commission"
        verbose_name_plural = "paiements de commission"
        ordering = ("-paid_at", "-pk")
        constraints = (
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="sales_payout_positive"),
        )

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.amount}"
