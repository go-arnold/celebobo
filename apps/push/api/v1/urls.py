from django.urls import path

from apps.push.api.v1.views import DeviceViewSet, PublicKeyViewSet

urlpatterns = [
    path("push/public-key/", PublicKeyViewSet.as_view({"get": "retrieve"}), name="push-public-key"),
    path(
        "me/devices/", DeviceViewSet.as_view({"get": "list", "post": "create"}), name="my-devices"
    ),
    path(
        "me/devices/<int:device_id>/",
        DeviceViewSet.as_view({"delete": "destroy"}),
        name="my-device",
    ),
]
