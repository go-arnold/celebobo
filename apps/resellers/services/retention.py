from datetime import datetime

from apps.audit.domain.retention import BATCH_SIZE, RetentionReport, years_before
from apps.audit.services.retention import purge_expired
from apps.resellers.domain.retention import REJECTED_APPLICATION_YEARS
from apps.resellers.repositories import ApplicationRepository

RULE = "resellers.rejected_applications"


class RejectedApplicationRetention:
    label = "Candidatures revendeur refusées depuis plus d'un an, supprimées"

    def __init__(self, applications: ApplicationRepository) -> None:
        self._applications = applications

    def apply(self, *, now: datetime, dry_run: bool) -> RetentionReport:
        cutoff = years_before(now, REJECTED_APPLICATION_YEARS)
        return purge_expired(
            rule=RULE,
            label=self.label,
            fetch=lambda after: self._applications.rejected_before(
                cutoff, after_id=after, limit=BATCH_SIZE
            ),
            delete=lambda ids: self._applications.delete_rejected(ids, before=cutoff),
            dry_run=dry_run,
        )
