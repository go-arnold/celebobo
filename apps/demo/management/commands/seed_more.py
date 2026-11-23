from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.demo.enrich import DemoEnricher


class Command(BaseCommand):
    help = (
        "Enrichit la démo créée par seed_demo : plus de produits et de photos réelles, plus de "
        "clients et de commandes, et toutes les tables encore vides."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--password", default="Boutique-Kin#2026")
        parser.add_argument("--rounds", type=int, default=3, help="Tours de 28 commandes.")

    def handle(self, *args: Any, **options: Any) -> None:
        enricher = DemoEnricher(
            password=options["password"], log=self.stdout.write, rounds=options["rounds"]
        )
        report = enricher.run()
        for name, count in sorted(report.counts.items()):
            self.stdout.write(f"{name:>28} : {count}")
