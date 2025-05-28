from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from logistics.api import views

router = DefaultRouter()
router.register(
    "contractors", views.ContractorsViewSet, basename="contractors"
)

router.register(
    "transport_applications",
    views.TransportApplicationViewSet,
    basename="transport_applications",
)
transport_application_router = routers.NestedSimpleRouter(
    router, r"transport_applications", lookup="transport_application"
)
transport_application_router.register(
    r"logistic_offers",
    views.LogisticsOffersViewSet,
    basename="logistic_offers",
)

router.register(r"analytics", views.AnalyticsViewSet, basename="analytics")

urlpatterns = router.urls + transport_application_router.urls
