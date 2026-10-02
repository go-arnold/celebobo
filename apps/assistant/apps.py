from django.apps import AppConfig


class AssistantConfig(AppConfig):
    name = "apps.assistant"
    label = "assistant"
    verbose_name = "Assistant"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.assistant.providers import register
        from core.container import container

        register(container)
