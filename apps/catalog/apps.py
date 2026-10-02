from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Catalogue"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.catalog.providers import register
        from core.container import container

        register(container)
