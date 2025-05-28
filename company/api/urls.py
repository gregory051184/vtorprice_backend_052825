from rest_framework_nested import routers

from company.api import views

router = routers.SimpleRouter()

router.register(r"companies", views.CompanyViewSet, basename="companies")

companies_router = routers.NestedSimpleRouter(
    router, r"companies", lookup="company"
)
companies_router.register(
    r"recyclables", views.CompanyRecyclablesViewSet, "recyclables"
)
companies_router.register(
    r"activity_types", views.CompanyActivityTypeViewSet, "activity_types"
)
companies_router.register(r"reviews", views.CompanyReviewsViewset, "reviews")

router.register(
    r"company_proposals",
    views.CompanyProposalViewSet,
    basename="company_proposals",
)

router.register(
    r"company_equipment_proposals",
    views.CompanyEquipmentProposalViewSet,
    basename="company_equipment_proposals",
)

router.register(
    r"company_subscribes_categories",
    views.SubscribeViewSet,
    basename="company_subscribes_categories"
)

router.register(
    r"company_subscribes",
    views.CompanySubscribeViewSet,
    basename="company_subscribes"
)

router.register(
    r"company_recyclables",
    views.CompanyRecyclablesViewSet,
    basename="company_recyclables",
)
router.register(
    r"company_documents",
    views.CompanyDocumentViewSet,
    basename="company_documents",
)
router.register(
    r"company_contacts",
    views.CompanyAdditionalContactViewSet,
    basename="company_contacts",
)
router.register(
    r"company_verification",
    views.CompanyVerificationRequestViewSet,
    basename="company_verification",
)
router.register(
    r"company_advantages",
    views.CompanyAdvantageViewSet,
    basename="company_advantages",
)
router.register(
    r"recycling_collection_types",
    views.RecyclingCollectionTypeViewSet,
    basename="recycling_collection_types",
)
router.register(
    r"company_activity_types",
    views.CompanyActivityTypeViewSet,
    basename="company_activity_types",
)
router.register(
    r"cities",
    views.CityViewSet,
    basename="cities",
)

router.register(r"regions", views.RegionViewSet, basename="regions")

router.register(r"districts", views.DistrictViewSet, basename="districts")

urlpatterns = router.urls
urlpatterns += companies_router.urls
