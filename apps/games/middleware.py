"""
WebSocket middleware — attaches the authenticated user (if any) from
a JWT token passed in the query string, e.g. ?token=<access_token>.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def get_user_from_token(token_str: str):
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from apps.accounts.models import User
        token = AccessToken(token_str)
        return User.objects.get(id=token['user_id'])
    except Exception:
        return AnonymousUser()


class WebSocketJWTAuthMiddleware(BaseMiddleware):
    """
    Reads the JWT `token` query parameter and populates scope['user'].
    Falls back to AnonymousUser if the token is absent or invalid.
    """

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token_list = params.get('token', [])

        if token_list:
            scope['user'] = await get_user_from_token(token_list[0])
        else:
            scope['user'] = AnonymousUser()

        return await super().__call__(scope, receive, send)
