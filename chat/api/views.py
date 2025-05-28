from django.db.models import Sum
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_nested.viewsets import NestedViewSetMixin

from chat.api.serializers import (
    ChatSerializer,
    MessageSerializer,
    CreateMessageSerializer,
    EditMessageSerializer,
)
from chat.models import Chat, Message
from common.views import MultiSerializerMixin


class ChatsViewSet(
    generics.ListAPIView, generics.RetrieveAPIView, GenericViewSet
):
    serializer_class = ChatSerializer
    queryset = Chat.objects.prefetch_related("messages").all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_anonymous:
            return queryset.none()
        queryset = queryset.filter_user_chats(user)
        queryset = (
            queryset.annotate_unread_messages(user)
            .annotate_latest_message()
            .order_by("-latest_created_at")
        )
        return queryset

    def get_total_unread_count(self):
        return self.get_queryset().aggregate(
            total_unread_count=Sum("unread_count")
        )["total_unread_count"]

    def list(self, request, *args, **kwargs):
        base_response = super().list(request, *args, **kwargs)
        base_response.data[
            "total_unread_count"
        ] = self.get_total_unread_count()
        return base_response


class MessageViewSet(
    NestedViewSetMixin,
    MultiSerializerMixin,
    GenericViewSet,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    generics.CreateAPIView,
    generics.UpdateAPIView,
):
    default_serializer_class = MessageSerializer
    serializer_classes = {
        "create": CreateMessageSerializer,
        "update": EditMessageSerializer,
        "partial_update": EditMessageSerializer,
    }
    queryset = Message.objects.all().prefetch_related("author")
    parent_lookup_kwargs = {"chat_pk": "chat__pk"}
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        """Overriding retrieve method, so we can mark messages as read after request"""

        message = self.get_object()
        if message.author != request.user and not message.is_read:
            message.is_read = True
            message.save()
        serializer = MessageSerializer(message)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """Overriding retrieve method, so we can mark messages as read after request"""
        queryset = self.get_queryset()

        paginator_class = self.pagination_class()
        paginated_queryset = paginator_class.paginate_queryset(
            queryset, request, view=self
        )
        messages_data = paginator_class.get_paginated_response(
            MessageSerializer(paginated_queryset, many=True).data
        )

        to_update = []
        for message in paginated_queryset:
            to_update.append(message.pk)
            message.is_read = True

        Message.objects.filter(id__in=to_update).exclude(
            author=request.user
        ).update(is_read=True)
        return messages_data
