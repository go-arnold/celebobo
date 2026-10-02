from django.apps import AppConfig


class MediaConfig(AppConfig):
    name = "apps.media"
    label = "media"
    verbose_name = "Fichiers"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.media.providers import register
        from core.container import container

        register(container)
