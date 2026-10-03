from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.catalog.models import Product
from apps.demo.seeder import DemoSeeder


class Command(BaseCommand):
    help = "Remplit une base vide avec un jeu de démonstration réaliste (images comprises)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--password", default="Boutique-Kin#2026")
        parser.add_argument("--no-images", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if Product.all_objects.exists():
            raise CommandError(
                "Le catalogue n'est pas vide : lancez cette commande sur une base neuve."
            )
        seeder = DemoSeeder(
            admin_email=options["admin_email"],
            password=options["password"],
            images=not options["no_images"],
            log=self.stdout.write,
        )
        report = seeder.run()
        for name, count in sorted(report.counts.items()):
            self.stdout.write(f"{name:>24} : {count}")
        self.stdout.write(self.style.SUCCESS("\nComptes de démonstration :"))
        for role, email, password in report.accounts:
            self.stdout.write(f"  {role:<9} {email:<40} {password}")
