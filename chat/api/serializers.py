from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from chat.models import Message, Chat
from common.serializers import (
    NonNullDynamicFieldsModelSerializer,
)
from user.api.serializers import UserSerializer


class MessageSerializer(NonNullDynamicFieldsModelSerializer):
    author = UserSerializer(fields=("id", "company", "email", "role"))

    class Meta:
        model = Message
        fields = ("id", "chat", "author", "content", "is_read", "created_at")


class EditMessageSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Message
        read_only_fields = ("id", "chat", "author", "content")

    def to_representation(self, instance):
        return MessageSerializer().to_representation(instance)

    def validate(self, attrs):
        if (
            self.instance.author.company
            == self.context["request"].user.company
        ):
            raise ValidationError(
                "Вы не можете пометить это сообщение как прочитанное"
            )
        return super().validate(attrs)


class ChatSerializer(NonNullDynamicFieldsModelSerializer):
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(default=0)

    class Meta:
        model = Chat
        read_only_fields = ["messages", "last_message", "unread_count"]

    def get_last_message(self, chat: Chat):
        try:
            last_message = chat.messages.latest("created_at")
        except Message.DoesNotExist:
            last_message = None
        if last_message:
            return MessageSerializer(last_message).data
        return MessageSerializer().data


class CreateMessageSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Message
        fields = ("chat", "content")

    def create(self, validated_data):
        validated_data["author"] = self.context["request"].user

        instance = super().create(validated_data)

        channel_layer = get_channel_layer()
        group_name = str(instance.chat.pk)

        # Transforming created instance to dict and sending it to websocket
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "chat_message",
                "message": self.to_representation(instance),
            },
        )
        return instance

    def to_representation(self, instance):
        return MessageSerializer().to_representation(instance)
