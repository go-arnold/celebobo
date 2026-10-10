from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.catalog.models import Product
from apps.demo.e2e import E2eSeeder, reset_database
from apps.demo.seeder import DemoSeeder, SeedReport


class Command(BaseCommand):
    help = "Remplit une base vide avec un jeu de démonstration réaliste (images comprises)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--admin-email")
        parser.add_argument("--password", default="Boutique-Kin#2026")
        parser.add_argument("--no-images", action="store_true")
        parser.add_argument(
            "--e2e",
            action="store_true",
            help="Vide la base puis crée le petit jeu fixe des tests bout-en-bout.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["e2e"]:
            if not settings.E2E_SEED_ALLOWED:
                raise CommandError("--e2e vide la base : activez E2E_SEED_ALLOWED pour ce stack.")
            reset_database()
            report = E2eSeeder(password=options["password"]).run()
        else:
            report = self._demo(options)
        for name, count in sorted(report.counts.items()):
            self.stdout.write(f"{name:>24} : {count}")
        self.stdout.write(self.style.SUCCESS("\nComptes de démonstration :"))
        for role, email, password in report.accounts:
            self.stdout.write(f"  {role:<9} {email:<40} {password}")

    def _demo(self, options: dict[str, Any]) -> SeedReport:
        if not options["admin_email"]:
            raise CommandError("--admin-email est obligatoire (sauf avec --e2e).")
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
        return seeder.run()
