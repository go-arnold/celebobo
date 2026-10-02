from django.apps import AppConfig


class PushConfig(AppConfig):
    name = "apps.push"
    label = "push"
    verbose_name = "Notifications push"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.push.providers import register
        from core.container import container

        register(container)
