from django.urls import path

from apps.audit.api.v1.views import AuditViewSet

urlpatterns = [
    path("bo/audit-logs/", AuditViewSet.as_view({"get": "changes"}), name="bo-audit-logs"),
    path(
        "bo/audit-logs/<id:entry_id>/",
        AuditViewSet.as_view({"get": "change"}),
        name="bo-audit-log",
    ),
    path(
        "bo/audit-logs/events/",
        AuditViewSet.as_view({"get": "events"}),
        name="bo-audit-events",
    ),
    path(
        "bo/audit-logs/object-types/",
        AuditViewSet.as_view({"get": "object_types"}),
        name="bo-audit-object-types",
    ),
]
