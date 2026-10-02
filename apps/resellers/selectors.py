from django.db.models import Count, Q, QuerySet

from apps.resellers.domain.commands import ApplicationFilters
from apps.resellers.domain.enums import ApplicationStatus
from apps.resellers.domain.errors import ApplicationNotFound
from apps.resellers.domain.read_models import ApplicationView, PersonRef
from apps.resellers.models import ResellerApplication


class ApplicationSelector:
    def page(
        self, filters: ApplicationFilters, *, offset: int, limit: int
    ) -> tuple[list[ApplicationView], int, dict[str, int]]:
        applications = self._filtered(filters)
        page = applications.select_related("reviewed_by")[offset : offset + limit]
        return [to_application_view(item) for item in page], applications.count(), self.counts()

    def one(self, application_id: int) -> ApplicationView:
        application = (
            ResellerApplication.objects.select_related("reviewed_by")
            .filter(pk=application_id)
            .first()
        )
        if application is None:
            raise ApplicationNotFound
        return to_application_view(application)

    def counts(self) -> dict[str, int]:
        totals = ResellerApplication.objects.aggregate(
            **{
                status.value: Count("pk", filter=Q(status=status.value))
                for status in ApplicationStatus
            }
        )
        return {name: int(value) for name, value in totals.items()}

    @staticmethod
    def _filtered(filters: ApplicationFilters) -> QuerySet[ResellerApplication]:
        applications = ResellerApplication.objects.all()
        if filters.status is not None:
            applications = applications.filter(status=filters.status.value)
        if filters.search:
            term = filters.search.strip()
            applications = applications.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
                | Q(phone_number__icontains=term)
                | Q(city__icontains=term)
            )
        return applications


def to_application_view(application: ResellerApplication) -> ApplicationView:
    reviewer = application.reviewed_by
    return ApplicationView(
        id=application.pk,
        first_name=application.first_name,
        last_name=application.last_name,
        email=application.email,
        phone_number=application.phone_number,
        city=application.city,
        message=application.message,
        status=application.application_status,
        applicant_id=application.applicant_id,
        reseller_id=application.reseller_id,
        reviewed_by=PersonRef(id=reviewer.pk, name=reviewer.get_full_name() or reviewer.email)
        if reviewer
        else None,
        reviewed_at=application.reviewed_at,
        decision_note=application.decision_note,
        created_at=application.created_at,
    )
