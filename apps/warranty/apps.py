from django.apps import AppConfig


class WarrantyConfig(AppConfig):
    name = "apps.warranty"
    label = "warranty"
    verbose_name = "Garantie et réclamations"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.warranty.providers import register
        from core.container import container

        register(container)
