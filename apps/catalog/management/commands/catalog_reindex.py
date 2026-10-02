from typing import Any

from django.core.management.base import BaseCommand

from apps.catalog.services.indexing import ProductIndexer
from core.container import container


class Command(BaseCommand):
    help = "Configure the product search index and push every product to it."

    def handle(self, *args: Any, **options: Any) -> None:
        total = container.resolve(ProductIndexer).rebuild()
        self.stdout.write(self.style.SUCCESS(f"{total} produits synchronisés."))
