from django.urls import path

from apps.credit.api.v1.views import StoreCreditViewSet

urlpatterns = [
    path(
        "me/store-credit/", StoreCreditViewSet.as_view({"get": "retrieve"}), name="my-store-credit"
    ),
]
