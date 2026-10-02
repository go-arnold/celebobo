from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = "apps.content"
    label = "content"
    verbose_name = "Contenu du site"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.content.providers import register
        from core.container import container

        register(container)
