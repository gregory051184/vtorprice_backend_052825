import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import close_old_connections
from rest_framework import status

from chat.models import Chat
from common.utils import DecimalEncoder


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await database_sync_to_async(close_old_connections)()
        self.user = self.scope["user"]

        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]

        # Group name should be str Group name must be a valid unicode string with length < 100
        # containing only ASCII alphanumerics, hyphens, underscores, or periods)
        self.room_group_name = str(self.chat_id)
        if not self.user or self.user.is_anonymous:
            await self.disconnect(status.HTTP_401_UNAUTHORIZED)
            return

        self.chat_db_obj, created = await database_sync_to_async(
            Chat.objects.get_or_create
        )(id=self.chat_id)

        # TODO: Check if user has access to this chat

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name, self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name, self.channel_name
        )

        await database_sync_to_async(close_old_connections)()

    # Receive message from room group
    async def chat_message(self, event):
        message: dict = event["message"]
        await self.send_json(json.dumps(message, cls=DecimalEncoder))
