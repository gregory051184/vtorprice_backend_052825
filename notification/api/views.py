from django.db.models import Q
from rest_framework import generics, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.views import MultiSerializerMixin
from notification.api.serializers import (
    NotificationSerializer,
    UpdateNotificationSerializer,
    NotificationCount,
)
from notification.models import Notification
from user.models import UserRole


class NotificationViewSet(
    GenericViewSet,
    generics.RetrieveAPIView,
    generics.ListAPIView,
    generics.UpdateAPIView,
    # ДОБАВИЛ ДЛЯ УДАЛЕНИЯ УВЕДОМЛЕНИЙ
    generics.DestroyAPIView,

    MultiSerializerMixin,
):
    queryset = Notification.objects.all()
    serializer_class = UpdateNotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name",)
    serializer_classes = {
        "list": NotificationSerializer,
        "retrieve": NotificationSerializer,
    }

    def get_queryset(self):
        qs = self.filter_queryset(super().get_queryset()).order_by(
            "-created_at"
        )

        user = self.request.user

        user_notification_query_node = Q(user=user)

        if user.is_anonymous:
            return qs.none()
        if user.role == UserRole.COMPANY_ADMIN or UserRole.COMPANY_STAFF:
            return qs.filter(
                Q(company=user.company) | user_notification_query_node
            )
        if user.role == UserRole.MANAGER:
            return qs.filter(
                Q(company__manager=user) | user_notification_query_node
            )
        if user.role == UserRole.LOGIST:
            return qs.filter(user_notification_query_node)

        if user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return qs

    def retrieve(self, request, *args, **kwargs):
        """Overriding retrieve method, so we can mark Notifications as read after request"""
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["GET"])
    def unread_count(self, request):
        # Посылает количество непрочитанных оповещений на страницу профиля компании
        return Response(
            NotificationCount(
                unread_count=self.get_queryset().filter(is_read=False).count()
            ).dict()
        )
