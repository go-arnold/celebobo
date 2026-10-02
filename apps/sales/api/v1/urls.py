from django.urls import path

from apps.sales.api.v1.views import (
    CommissionViewSet,
    ConversionViewSet,
    PayoutViewSet,
    SaleViewSet,
)

urlpatterns = [
    path("bo/sales/", SaleViewSet.as_view({"get": "list", "post": "create"}), name="bo-sales"),
    path("bo/sales/bulk/", SaleViewSet.as_view({"post": "bulk"}), name="bo-sales-bulk"),
    path(
        "bo/sales/<id:sale_id>/",
        SaleViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="bo-sale",
    ),
    path(
        "bo/sales/<id:sale_id>/refund/",
        SaleViewSet.as_view({"post": "refund"}),
        name="bo-sale-refund",
    ),
    path(
        "bo/orders/convertible/",
        ConversionViewSet.as_view({"get": "list"}),
        name="bo-orders-convertible",
    ),
    path(
        "bo/orders/<id:order_id>/convert-to-sales/",
        ConversionViewSet.as_view({"post": "create"}),
        name="bo-order-convert",
    ),
    path(
        "bo/commissions/",
        CommissionViewSet.as_view({"get": "list"}),
        name="bo-commissions",
    ),
    path(
        "bo/commissions/summary/",
        CommissionViewSet.as_view({"get": "summary"}),
        name="bo-commissions-summary",
    ),
    path(
        "bo/commissions/series/",
        CommissionViewSet.as_view({"get": "series"}),
        name="bo-commissions-series",
    ),
    path(
        "bo/commissions/overview/",
        CommissionViewSet.as_view({"get": "overview"}),
        name="bo-commissions-overview",
    ),
    path(
        "bo/payouts/",
        PayoutViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-payouts",
    ),
]
