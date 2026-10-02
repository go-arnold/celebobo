from collections.abc import Iterator, Sequence

from django.apps import apps
from django.urls import URLResolver, include, path, register_converter
from django.utils.module_loading import module_has_submodule
from rest_framework.settings import api_settings

from core.api.converters import IdConverter

register_converter(IdConverter, "id")


def versioned_urlpatterns() -> list[URLResolver]:
    return [
        path(
            f"api/{version}/",
            include(
                ([path("", include(module)) for module in _url_modules(version)], version),
                namespace=version,
            ),
        )
        for version in _allowed_versions()
    ]


def _allowed_versions() -> Sequence[str]:
    versions: Sequence[str] = api_settings.ALLOWED_VERSIONS or ()
    return versions


def _url_modules(version: str) -> Iterator[str]:
    submodule = f"api.{version}.urls"
    for app_config in apps.get_app_configs():
        if module_has_submodule(app_config.module, submodule):
            yield f"{app_config.name}.{submodule}"
