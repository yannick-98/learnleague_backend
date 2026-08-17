from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/game/(?P<session_code>[A-Za-z0-9]{6})/$', consumers.GameConsumer.as_asgi()),
]
