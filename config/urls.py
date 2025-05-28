"""vtorprice URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from chat.routing import websocket_urlpatterns

api_urlpatterns = [
    path("", include("user.api.urls")),
    path("", include("company.api.urls")),
    path("", include("product.api.urls")),
    path("", include("exchange.api.urls")),
    path("", include("chat.api.urls")),
    path("", include("logistics.api.urls")),
    path("services/", include("services.api.urls")),
    path("", include("notification.api.urls")),
    path("", include("statistic.api.urls")),
    path("", include("finance.api.urls")),
]

urlpatterns = [
    path("api/admin/", admin.site.urls),
    path("api/", include(api_urlpatterns)),
]

schema_view = get_schema_view(
    openapi.Info(
        title="API VtorPrice",
        default_version="v1",
        description="Данная страница содержит автогенерируемую документацию по API VtorPrice",
        license=openapi.License(name="Commercial License"),
    ),
    url=settings.BASE_URL,
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns += [
    re_path(
        r"^api/swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    re_path(
        r"^api/swagger/$",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^api/redoc/$",
        schema_view.with_ui("redoc", cache_timeout=0),
        name="schema-redoc",
    ),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += websocket_urlpatterns

if settings.DEBUG:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
