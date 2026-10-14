from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.catalog.domain.management import ProductChanges
from apps.catalog.facades import ProductAdminFacade
from apps.catalog.models import Product
from apps.demo.uploads import admin_store, upload
from apps.media.domain.policies import UploadPurpose
from core.container import container

MAX_IMAGES = 4
EXTENSIONS = {".jpg", ".jpeg"}


class Command(BaseCommand):
    help = (
        "Remplace les images des produits par celles d'un dossier : un sous-dossier par slug, "
        "fichiers JPEG pris par ordre de nom (le premier est l'image principale)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("folder", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        plan = self._plan(options["folder"])
        products = {product.slug: product for product in Product.objects.filter(slug__in=plan)}
        unknown = sorted(set(plan) - set(products))
        if unknown:
            raise CommandError(f"Produits introuvables : {', '.join(unknown)}")
        for slug, files in plan.items():
            current = products[slug].images.count()
            self.stdout.write(f"{slug:<40} {current} -> {len(files)} images")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Simulation : rien n'a été modifié."))
            return
        actor, store = admin_store("products")
        facade = container.resolve(ProductAdminFacade)
        purpose = UploadPurpose.PRODUCT_IMAGE.value
        for slug, files in plan.items():
            media_ids = [
                upload(store, f"{slug}-{position}", path.read_bytes(), purpose=purpose)
                for position, path in files
            ]
            facade.update(actor, products[slug].pk, ProductChanges(image_ids=tuple(media_ids)))
            self.stdout.write(self.style.SUCCESS(f"{slug} : {len(media_ids)} images"))

    def _plan(self, folder: Path) -> dict[str, list[tuple[int, Path]]]:
        if not folder.is_dir():
            raise CommandError(f"Dossier introuvable : {folder}")
        plan: dict[str, list[tuple[int, Path]]] = {}
        for directory in sorted(path for path in folder.iterdir() if path.is_dir()):
            files = sorted(
                path for path in directory.iterdir() if path.suffix.lower() in EXTENSIONS
            )
            if not files or len(files) > MAX_IMAGES:
                raise CommandError(f"{directory.name} : entre 1 et {MAX_IMAGES} images JPEG.")
            plan[directory.name] = list(enumerate(files, 1))
        if not plan:
            raise CommandError("Aucun sous-dossier de produit.")
        return plan
