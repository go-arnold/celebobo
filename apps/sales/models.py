from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.enums import CommissionKind, RefundKind, SaleStatus
from apps.sales.domain.payouts import DeliveryCreditKind, StatementStatus

PAYMENT_CHOICES = [(item.value, item.label) for item in PaymentMethod]
STATUS_CHOICES = [(item.value, item.value) for item in SaleStatus]
REFUND_CHOICES = [(item.value, item.value) for item in RefundKind]
COMMISSION_CHOICES = [(item.value, item.value) for item in CommissionKind]
STATEMENT_CHOICES = [(item.value, item.value) for item in StatementStatus]
DELIVERY_CREDIT_CHOICES = [(item.value, item.value) for item in DeliveryCreditKind]
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
    # units of an order-linked sale given back through a line return of the order
    returned_quantity = models.PositiveIntegerField(default=0)
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
    # pending until then, validated (payable) after; a reversal shares the date of the earning it
    # offsets, so it lowers what is pending or what is validated, never both
    available_at = models.DateTimeField(db_index=True)
    # the payout statement that settles this entry
    statement = models.ForeignKey(
        "PayoutStatement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commission_entries",
    )
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


class PayoutStatement(models.Model):
    """What a reseller is paid on one payout date: validated commissions and delivery fees."""

    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payout_statements"
    )
    payout_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=STATEMENT_CHOICES, default=StatementStatus.PREPARED.value
    )
    commissions = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    delivery_fees = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    total = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    payout = models.OneToOneField(
        Payout, null=True, blank=True, on_delete=models.PROTECT, related_name="statement"
    )
    prepared_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "relevé de paiement"
        verbose_name_plural = "relevés de paiement"
        ordering = ("-payout_date", "-pk")
        constraints = (
            models.UniqueConstraint(
                fields=("reseller", "payout_date"),
                condition=~models.Q(status=StatementStatus.CANCELLED.value),
                name="sales_statement_once_per_date",
            ),
        )

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.payout_date} {self.total}"


class DeliveryCredit(models.Model):
    """The delivery fee of an order the reseller delivered, paid back with their commissions."""

    reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="delivery_credits"
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    order_number = models.CharField(max_length=16)
    kind = models.CharField(max_length=10, choices=DELIVERY_CREDIT_CHOICES)
    amount = models.DecimalField(max_digits=DIGITS, decimal_places=PLACES)
    note = models.CharField(max_length=255, blank=True)
    available_at = models.DateTimeField(db_index=True)
    statement = models.ForeignKey(
        PayoutStatement,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_credits",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "frais de livraison reversés"
        verbose_name_plural = "frais de livraison reversés"
        ordering = ("-created_at", "-pk")
        constraints = (
            models.UniqueConstraint(
                fields=("order", "kind"),
                condition=models.Q(order__isnull=False),
                name="sales_delivery_credit_once_per_order",
            ),
        )

    def __str__(self) -> str:
        return f"{self.reseller_id} {self.order_number} {self.amount:+}"
