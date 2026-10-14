from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.catalog.domain.management import CategoryChanges
from apps.catalog.facades import CategoryAdminFacade
from apps.catalog.models import Category
from apps.demo.uploads import admin_store, upload
from apps.media.domain.policies import UploadPurpose
from core.container import container

EXTENSIONS = {".jpg", ".jpeg"}


class Command(BaseCommand):
    help = "Remplace l'image des catégories par celles d'un dossier : un fichier JPEG par slug."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("folder", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        folder: Path = options["folder"]
        if not folder.is_dir():
            raise CommandError(f"Dossier introuvable : {folder}")
        files = {
            path.stem: path
            for path in sorted(folder.iterdir())
            if path.is_file() and path.suffix.lower() in EXTENSIONS
        }
        if not files:
            raise CommandError("Aucune image JPEG.")
        categories = {item.slug: item for item in Category.objects.filter(slug__in=files)}
        unknown = sorted(set(files) - set(categories))
        if unknown:
            raise CommandError(f"Catégories introuvables : {', '.join(unknown)}")
        for slug in files:
            self.stdout.write(f"{slug:<30} {'remplacée' if categories[slug].image else 'ajoutée'}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Simulation : rien n'a été modifié."))
            return
        actor, store = admin_store("categories")
        facade = container.resolve(CategoryAdminFacade)
        purpose = UploadPurpose.CATEGORY_IMAGE.value
        for slug, path in files.items():
            media_id = upload(store, slug, path.read_bytes(), purpose=purpose)
            facade.update(actor, categories[slug].pk, CategoryChanges(image_id=media_id))
            self.stdout.write(self.style.SUCCESS(f"{slug} : image mise à jour"))
