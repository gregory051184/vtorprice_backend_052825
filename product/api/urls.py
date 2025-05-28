from rest_framework.routers import DefaultRouter

from product.api import views

router = DefaultRouter()

router.register(
    r"recyclables", views.RecyclablesViewSet, basename="recyclables"
)
router.register(
    r"recyclables_categories",
    views.RecyclablesCategoryViewSet,
    basename="recyclables_categories",
)

router.register(r"equipment", views.EquipmentViewSet, basename="equipment")
router.register(
    r"equipment_categories",
    views.EquipmentCategoryViewSet,
    basename="equipment_categories",
)
router.register(
    r"recycling_codes", views.RecyclingCodeViewSet, basename="recycling_codes"
)

urlpatterns = router.urls
