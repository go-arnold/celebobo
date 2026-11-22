from django.urls import path

from apps.documents.api.v1.views import (
    ExportViewSet,
    InvoiceViewSet,
    JobViewSet,
    PersonalDataViewSet,
    ReceiptVerificationViewSet,
    ReceiptViewSet,
)

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
        "me/data-export/",
        PersonalDataViewSet.as_view({"get": "retrieve", "post": "create"}),
        name="my-data-export",
    ),
    path(
        "me/data-export/<uuid:job_id>/download/",
        PersonalDataViewSet.as_view({"get": "download"}),
        name="my-data-export-download",
    ),
    path(
        "me/orders/<str:number>/invoice/",
        InvoiceViewSet.as_view({"get": "mine"}),
        name="my-order-invoice",
    ),
    path(
        "bo/orders/<id:order_id>/invoice/",
        InvoiceViewSet.as_view({"get": "backoffice"}),
        name="bo-order-invoice",
    ),
    path(
        "me/orders/<str:number>/receipt/",
        ReceiptViewSet.as_view({"get": "mine"}),
        name="my-order-receipt",
    ),
    path(
        "bo/orders/<id:order_id>/receipt/",
        ReceiptViewSet.as_view({"get": "backoffice"}),
        name="bo-order-receipt",
    ),
    path(
        "receipts/verify/",
        ReceiptVerificationViewSet.as_view({"post": "create"}),
        name="receipt-verify",
    ),
]
