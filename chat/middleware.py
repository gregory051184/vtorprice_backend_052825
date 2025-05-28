from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


@database_sync_to_async
def get_user(token):
    """
    Parsing JWT token, checking it on expiration date.
    If token is valid -> getting user id from it.
    Returning User object.

    Used code from channels documentation: https://channels.readthedocs.io/en/stable/topics/authentication.html
    """

    try:
        access_token = AccessToken(token)
        access_token.check_exp()
    except TokenError:
        return AnonymousUser()
    user_id = access_token.payload["user_id"]

    return User.objects.get(id=user_id)


class QueryAuthMiddleware:
    """
    Custom middleware that takes user token from the query string.
    Token being passed using ?token param.
    Used code from channels documentation: https://channels.readthedocs.io/en/stable/topics/authentication.html
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send, *args, **kwargs):
        if "user" in scope:
            return await self.app(scope, receive, send)

        token = scope["query_string"].decode().replace("token=", "")

        scope["user"] = await get_user(token)

        return await self.app(scope, receive, send)
