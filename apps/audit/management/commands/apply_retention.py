from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.audit.facades import AuditFacade
from core.container import container


class Command(BaseCommand):
    help = (
        "Apply the retention periods of the privacy policy now (the daily tasks do it too). "
        "With --dry-run, only print what would be affected."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--rule",
            action="append",
            dest="rules",
            help="Rule to apply (repeatable). Default: every rule.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Change nothing, list what would be affected."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        audit = container.resolve(AuditFacade)
        available = audit.retention_rules()
        rules: list[str] = options["rules"] or available
        if unknown := sorted(set(rules) - set(available)):
            raise CommandError(
                f"Règle inconnue : {', '.join(unknown)} (disponibles : {', '.join(available)})"
            )
        dry_run: bool = options["dry_run"]
        for rule in rules:
            report = audit.apply_retention(rule, dry_run=dry_run)
            verb = "à traiter" if dry_run else "traités"
            self.stdout.write(
                self.style.SUCCESS(f"{rule} — {report.label} : {report.affected} {verb}")
            )
            for sample in report.samples:
                self.stdout.write(f"  · {sample}")
            if dry_run and report.affected > len(report.samples):
                self.stdout.write(f"  … et {report.affected - len(report.samples)} autres")
