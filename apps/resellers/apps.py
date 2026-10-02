from django.apps import AppConfig


class ResellersConfig(AppConfig):
    name = "apps.resellers"
    label = "resellers"
    verbose_name = "Programme revendeur"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.resellers.providers import register
        from core.container import container

        register(container)
