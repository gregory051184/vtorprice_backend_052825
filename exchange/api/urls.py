from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from exchange.api import views

router = DefaultRouter()

router.register(
    r"recyclables_applications",
    views.RecyclablesApplicationViewSet,
    basename="recyclables_applications",
)

router.register(
    r"all_recyclables_applications",
    views.AllRecyclablesApplicationsViewSet,
    basename="all_recyclables_applications"
)

router.register(
    r"equipment_applications",
    views.EquipmentApplicationViewSet,
    basename="equipment_applications",
)

router.register(
    r"special_applications",
    views.SpecialViewSet,
    basename="special_applications",
)

router.register(
    r"companies_special_applications",
    views.SpecialApplicationsViewSet,
    basename="companies_special_applications",
)

router.register(
    r"recyclables_deals",
    views.RecyclablesDealViewSet,
    basename="recyclables_deals",
)

recyclable_deals_router = routers.NestedSimpleRouter(
    router, r"recyclables_deals", lookup="object"
)
recyclable_deals_router.register(
    r"reviews", views.ReviewViewSet, basename="reviews"
)

router.register(
    r"equipment_deals",
    views.EquipmentDealViewSet,
    basename="equipment_deals",
)

equipment_deals_router = routers.NestedSimpleRouter(
    router, r"equipment_deals", lookup="object"
)
equipment_deals_router.register(
    r"reviews", views.ReviewViewSet, basename="reviews"
)

router.register(
    r"exchange_recyclables",
    views.ExchangeRecyclablesViewSet,
    basename="exchange_recyclables",
)

urlpatterns = (
        router.urls + recyclable_deals_router.urls + equipment_deals_router.urls
)
