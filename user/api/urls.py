from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt import views as simplejwt_views

from user.api import views


router = DefaultRouter()

router.register(r"users", views.AuthViewSet, basename="users")

urlpatterns = [
    path(
        "users/token/refresh/",
        simplejwt_views.TokenRefreshView.as_view(),
        name="token-refresh",
    ),
    path("users/", views.UserView.as_view(), name="users"),
    path("users/<int:pk>/", views.get),
    path("users/update_user_role/<int:pk>/", views.update_user_role),
]

urlpatterns += router.urls
