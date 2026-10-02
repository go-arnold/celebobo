from collections.abc import Collection

from django.db.models import Q

from apps.catalog.models import Category, ProductImage, ProductVariant


class CatalogMediaReferences:
    def referenced(self, urls: Collection[str]) -> set[str]:
        wanted = list(urls)
        found = set(ProductImage.objects.filter(url__in=wanted).values_list("url", flat=True))
        found |= set(Category.all_objects.filter(image__in=wanted).values_list("image", flat=True))
        found |= set(
            ProductVariant.objects.filter(Q(image__in=wanted)).values_list("image", flat=True)
        )
        return found
