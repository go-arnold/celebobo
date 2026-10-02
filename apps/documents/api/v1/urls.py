from django.urls import path

from apps.documents.api.v1.views import ExportViewSet, InvoiceViewSet, JobViewSet

urlpatterns = [
    path("bo/sales/export/", ExportViewSet.as_view({"post": "sales"}), name="bo-sales-export"),
    path(
        "bo/products/export/",
        ExportViewSet.as_view({"post": "products"}),
        name="bo-products-export",
    ),
    path(
        "bo/products/import/",
        ExportViewSet.as_view({"post": "products_import"}),
        name="bo-products-import",
    ),
    path(
        "bo/analytics/export/",
        ExportViewSet.as_view({"post": "analytics"}),
        name="bo-analytics-export",
    ),
    path("jobs/", JobViewSet.as_view({"get": "list"}), name="jobs"),
    path("jobs/<uuid:job_id>/", JobViewSet.as_view({"get": "retrieve"}), name="job"),
    path(
        "jobs/<uuid:job_id>/download/",
        JobViewSet.as_view({"get": "download"}),
        name="job-download",
    ),
    path(
        "me/orders/<str:number>/invoice/",
        InvoiceViewSet.as_view({"get": "mine"}),
        name="my-order-invoice",
    ),
    path(
        "bo/orders/<int:order_id>/invoice/",
        InvoiceViewSet.as_view({"get": "backoffice"}),
        name="bo-order-invoice",
    ),
]
