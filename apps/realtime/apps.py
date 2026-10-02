from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    name = "apps.realtime"
    label = "realtime"
    verbose_name = "Temps réel"

    def ready(self) -> None:
        from apps.realtime.providers import register
        from core.container import container

        register(container)
