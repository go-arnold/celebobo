from django.urls import path

from apps.media.api.v1.views import UploadViewSet

urlpatterns = [
    path("uploads/sign/", UploadViewSet.as_view({"post": "sign"}), name="upload-sign"),
    path("uploads/complete/", UploadViewSet.as_view({"post": "complete"}), name="upload-complete"),
    path(
        "uploads/complete/batch/",
        UploadViewSet.as_view({"post": "complete_many"}),
        name="upload-complete-batch",
    ),
]
