from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from common.serializers import NonNullDynamicFieldsModelSerializer
from notification.models import Notification

from pydantic import BaseModel


class NotificationSerializer(NonNullDynamicFieldsModelSerializer):
    object_url = serializers.SerializerMethodField()
    content_type = serializers.SerializerMethodField()

    class Meta:
        model = Notification

    def get_object_url(self, instance: Notification):
        from chat.models import Message

        if not instance.content_object:
            return None

        # For new message we redirect to chat
        if instance.content_type == ContentType.objects.get_for_model(Message):
            if not instance.content_object.chat:
                return None
            return instance.content_object.chat.get_absolute_url()
        # For all other cases redirect to object
        try:
            return instance.content_object.get_absolute_url()
        except AttributeError:
            return ""

    def get_content_type(self, instance):
        from chat.models import Message, Chat

        # For new message we give contentType of chat
        if instance.content_type == ContentType.objects.get_for_model(Message):
            return ContentType.objects.get_for_model(Chat).model
        # For all other cases contentType of object
        return instance.content_type.model


class UpdateNotificationSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Notification
        fields = ("is_read",)

    def to_representation(self, instance):
        return NotificationSerializer().to_representation(instance)

# Модель количества непрочитанных оповещений
class NotificationCount(BaseModel):
    unread_count: int
