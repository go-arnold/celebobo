from django.apps import AppConfig


class SalesConfig(AppConfig):
    name = "apps.sales"
    label = "sales"
    verbose_name = "Ventes"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.sales.providers import register
        from core.container import container

        register(container)
