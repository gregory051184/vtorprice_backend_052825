from rest_framework import routers

from notification.api.views import NotificationViewSet

notification_router = routers.DefaultRouter()
notification_router.register(
    "notification", NotificationViewSet, basename="notification"
)
urlpatterns = notification_router.urls
