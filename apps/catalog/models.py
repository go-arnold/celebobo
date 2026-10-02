from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from safedelete.config import SOFT_DELETE
from safedelete.models import SafeDeleteModel

from apps.catalog.domain.enums import Badge, CategoryIcon, ReviewStatus, StockReason
from apps.catalog.domain.rules import current_price

BADGE_CHOICES = [(item.value, item.label) for item in Badge]
ICON_CHOICES = [(item.value, item.value) for item in CategoryIcon]
STOCK_REASON_CHOICES = [(item.value, item.label) for item in StockReason]
REVIEW_STATUS_CHOICES = [(item.value, item.value) for item in ReviewStatus]
MONEY_DIGITS = 10
MONEY_PLACES = 2


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(SafeDeleteModel, TimestampedModel):
    _safedelete_policy = SOFT_DELETE

    name = models.CharField("nom", max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    image = models.URLField(max_length=500, blank=True)
    icon = models.CharField(max_length=16, choices=ICON_CHOICES, default=CategoryIcon.MOBILE.value)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ("position", "name")
        constraints = (
            models.UniqueConstraint(
                Lower("name"),
                condition=models.Q(deleted__isnull=True),
                name="catalog_category_name_ci_unique",
            ),
        )

    def __str__(self) -> str:
        return self.name


class Product(SafeDeleteModel, TimestampedModel):
    _safedelete_policy = SOFT_DELETE

    name = models.CharField("nom", max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    description = models.CharField("description courte", max_length=255)
    long_description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    badge = models.CharField(max_length=16, choices=BADGE_CHOICES, blank=True)
    price = models.DecimalField("prix", max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES)
    sale_price = models.DecimalField(
        "prix soldé", null=True, blank=True, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    cost_price = models.DecimalField(
        "prix d'achat", null=True, blank=True, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    current_price = models.DecimalField(
        editable=False, db_index=True, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    care_instructions = models.TextField(blank=True)
    delivery_policy_primary = models.TextField(blank=True)
    delivery_policy_secondary = models.TextField(blank=True)
    free_shipping = models.BooleanField(default=False)
    shipping_fee = models.DecimalField(
        null=True, blank=True, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    stock = models.PositiveIntegerField(default=0)
    stock_threshold = models.PositiveIntegerField(default=5)
    sell_by = models.DateField("vendre avant le", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal(0))
    reviews_count = models.PositiveIntegerField(default=0)
    sales_count = models.PositiveIntegerField(default=0, db_index=True)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        verbose_name = "produit"
        verbose_name_plural = "produits"
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=("is_active", "category"), name="catalog_product_active_cat"),
            models.Index(fields=("rating_avg",), name="catalog_product_rating"),
            GinIndex(fields=("search_vector",), name="catalog_product_search"),
        )
        constraints = (
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="catalog_product_price_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(sale_price__isnull=True)
                | models.Q(sale_price__gt=0, sale_price__lt=models.F("price")),
                name="catalog_product_sale_price_below_price",
            ),
            models.CheckConstraint(
                condition=models.Q(cost_price__isnull=True) | models.Q(cost_price__gte=0),
                name="catalog_product_cost_price_positive",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.current_price = current_price(self.price, self.sale_price)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {"price", "sale_price"} & set(update_fields):
            kwargs["update_fields"] = {*update_fields, "current_price"}
        super().save(*args, **kwargs)

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def is_trashed(self) -> bool:
        return getattr(self, "deleted", None) is not None


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    url = models.URLField(max_length=500)
    alt = models.CharField(max_length=255, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("product", "position"), name="catalog_image_unique_position"
            ),
        )

    def __str__(self) -> str:
        return self.url


class ProductFeature(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="features")
    name = models.CharField(max_length=255)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")

    def __str__(self) -> str:
        return self.name


class ProductOption(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=60)
    values = models.JSONField(default=list)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = (
            models.UniqueConstraint(fields=("product", "name"), name="catalog_option_unique_name"),
        )

    def __str__(self) -> str:
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    attributes = models.JSONField(default=dict)
    price = models.DecimalField(
        null=True, blank=True, max_digits=MONEY_DIGITS, decimal_places=MONEY_PLACES
    )
    stock = models.PositiveIntegerField(default=0)
    image = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")

    def __str__(self) -> str:
        return f"{self.product} — {self.label}"


class StockMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True, on_delete=models.PROTECT, related_name="movements"
    )
    delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=16, choices=STOCK_REASON_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_type = models.CharField(max_length=32, blank=True)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = (models.Index(fields=("product", "-created_at"), name="catalog_stock_product"),)

    def __str__(self) -> str:
        return f"{self.product} {self.delta:+d}"


class Review(TimestampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    message = models.TextField(max_length=2000)
    verified = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16, choices=REVIEW_STATUS_CHOICES, default=ReviewStatus.PUBLISHED.value
    )

    class Meta:
        verbose_name = "avis"
        verbose_name_plural = "avis"
        ordering = ("-created_at", "-pk")
        constraints = (
            models.UniqueConstraint(fields=("product", "user"), name="catalog_review_one_per_user"),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="catalog_review_rating_range",
            ),
        )

    def __str__(self) -> str:
        return f"{self.product} — {self.rating}/5"


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = (
            models.UniqueConstraint(fields=("user", "product"), name="catalog_favorite_unique"),
        )

    def __str__(self) -> str:
        return f"{self.user} ♥ {self.product}"


def visible_products() -> models.QuerySet[Product]:
    return Product.objects.filter(is_active=True, category__is_active=True, category__deleted=None)
