from django.apps import AppConfig


class MessagingConfig(AppConfig):
    name = "apps.messaging"
    label = "messaging"
    verbose_name = "Messagerie"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.messaging.providers import register
        from core.container import container

        register(container)
