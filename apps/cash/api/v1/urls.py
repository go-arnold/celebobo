from django.urls import path

from apps.cash.api.v1.views import CashViewSet

urlpatterns = [
    path("bo/cash/", CashViewSet.as_view({"get": "overview"}), name="bo-cash"),
    path("bo/cash/summary/", CashViewSet.as_view({"get": "summary"}), name="bo-cash-summary"),
    path(
        "bo/cash/remittances/", CashViewSet.as_view({"post": "remit"}), name="bo-cash-remittances"
    ),
]
