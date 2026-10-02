from django.urls import path

from apps.realtime.consumers import GatewayConsumer

websocket_urlpatterns = [path("ws/", GatewayConsumer.as_asgi())]
