from rest_framework.routers import DefaultRouter
from statistic.api.views import StatisticsViewSet

router = DefaultRouter()
router.register(r"statistics", StatisticsViewSet, basename="statistics")
urlpatterns = router.urls
