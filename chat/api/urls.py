from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from chat.api import views

router = DefaultRouter()

router.register(r"chats", views.ChatsViewSet, basename="chats")

chats_router = routers.NestedSimpleRouter(router, r"chats", lookup="chat")
chats_router.register(r"messages", views.MessageViewSet, basename="messages")
urlpatterns = [
    path(r"", include(router.urls)),
    path(r"", include(chats_router.urls)),
]
