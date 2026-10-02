from django.contrib import admin
from django.urls import include, path

from core.api.routing import versioned_urlpatterns

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("health/", include("core.health.urls")),
    *versioned_urlpatterns(),
]

handler404 = "core.api.exceptions.not_found"
handler500 = "core.api.exceptions.server_error"
