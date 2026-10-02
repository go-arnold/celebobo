from typing import Any

from django.contrib import admin
from django.db import transaction
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

from apps.catalog.domain.events import CategoryChanged, ProductChanged, ProductRemoved
from apps.catalog.models import (
    Category,
    Product,
    ProductFeature,
    ProductImage,
    ProductOption,
    ProductVariant,
    Review,
)
from core.container import container
from core.events.contracts import EventPublisher


def _publish(event: Any) -> None:
    container.resolve(EventPublisher).publish(event)


class ProductImageInline(admin.TabularInline[ProductImage, Product]):
    model = ProductImage
    extra = 0


class ProductFeatureInline(admin.TabularInline[ProductFeature, Product]):
    model = ProductFeature
    extra = 0


class ProductOptionInline(admin.TabularInline[ProductOption, Product]):
    model = ProductOption
    extra = 0


class ProductVariantInline(admin.TabularInline[ProductVariant, Product]):
    model = ProductVariant
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin[Category]):
    list_display = ("name", "slug", "icon", "is_active", "position")
    list_editable = ("is_active", "position")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    def save_model(
        self, request: HttpRequest, obj: Category, form: ModelForm[Category], change: bool
    ) -> None:
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            _publish(CategoryChanged(category_id=obj.pk, actor_id=request.user.pk))

    def delete_model(self, request: HttpRequest, obj: Category) -> None:
        with transaction.atomic():
            category_id = obj.pk
            super().delete_model(request, obj)
            _publish(CategoryChanged(category_id=category_id, actor_id=request.user.pk))


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin[Product]):
    list_display = ("name", "category", "price", "sale_price", "stock", "is_active", "created_at")
    list_filter = ("is_active", "category", "badge", "free_shipping")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("current_price", "rating_avg", "reviews_count", "sales_count")
    inlines = (ProductImageInline, ProductFeatureInline, ProductOptionInline, ProductVariantInline)

    def save_related(
        self, request: HttpRequest, form: ModelForm[Product], formsets: Any, change: bool
    ) -> None:
        with transaction.atomic():
            super().save_related(request, form, formsets, change)
            _publish(ProductChanged(product_id=form.instance.pk, actor_id=request.user.pk))

    def delete_model(self, request: HttpRequest, obj: Product) -> None:
        with transaction.atomic():
            product_id = obj.pk
            super().delete_model(request, obj)
            _publish(ProductRemoved(product_id=product_id, actor_id=request.user.pk))

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        with transaction.atomic():
            product_ids = list(queryset.values_list("pk", flat=True))
            super().delete_queryset(request, queryset)
            for product_id in product_ids:
                _publish(ProductRemoved(product_id=product_id, actor_id=request.user.pk))


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin[Review]):
    list_display = ("product", "user", "rating", "status", "verified", "created_at")
    list_filter = ("status", "rating", "verified")
    raw_id_fields = ("product", "user")
