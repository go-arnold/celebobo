import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings

from apps.realtime.adapters.auth import TicketAuthMiddleware
from apps.realtime.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_application,
        "websocket": OriginValidator(
            TicketAuthMiddleware(URLRouter(websocket_urlpatterns)),
            settings.WEBSOCKET_ALLOWED_ORIGINS,
        ),
    }
)
