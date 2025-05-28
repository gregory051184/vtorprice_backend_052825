from django_filters.rest_framework import FilterSet, DjangoFilterBackend
from rest_framework import filters, generics, viewsets
from rest_framework.filters import BaseFilterBackend
from rest_framework.permissions import AllowAny

from rest_framework.decorators import action
from common.views import BaseQuerySetMixin
from exchange.models import RecyclablesApplication, DealType
from product.api.serializers import (
    RecyclablesSerializer,
    RecyclablesCategorySerializer,
    EquipmentCategorySerializer,
    EquipmentSerializer,
    # RecyclingCodeSerializer,
)
from product.models import (
    Recyclables,
    RecyclablesCategory,
    EquipmentCategory,
    Equipment,
    RecyclingCode,
)

from exchange.utils import (
    validate_period,
    get_truncation_class,
    get_lower_date_bound,
)

from rest_framework.response import Response


class RecyclablesCategoryViewSet(
    BaseQuerySetMixin,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    viewsets.GenericViewSet,
):
    queryset = RecyclablesCategory.objects.root_nodes().prefetch_related(
        "recyclables"
    )
    serializer_class = RecyclablesCategorySerializer
    permission_classes = (AllowAny,)
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )
    search_fields = ("name",)
    ordering_fields = "__all__"


class RecyclablesFilterSet(FilterSet):
    class Meta:
        model = Recyclables
        fields = {
            "category": ["exact"],
            "category__parent": ["exact"],
            "applications__city": ["exact"],
            "applications__urgency_type": ["exact"],
        }


# ДОБАВИЛ
class ApplicationsRecyclablesFilterSet(FilterSet):
    class Meta:
        model = Recyclables
        fields = {
            "category": ["exact"],
            "category__parent": ["exact"],
            "applications__city": ["exact"],
            "applications__urgency_type": ["exact"]
        }


class RecyclablesViewSet(viewsets.ModelViewSet):
    queryset = Recyclables.objects.all()
    serializer_class = RecyclablesSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("name",)
    ordering_fields = "__all__"
    pagination_class = None

    #filterset_class = RecyclablesFilterSet

    @property
    def filterset_class(self):
        if self.action == "generate_offers":
            return RecyclablesFilterSet
        return RecyclablesFilterSet

    def get_queryset(self):
        if self.action == "generate_offers":
            # return Recyclables.objects.recyclables_generate_offers()
            return Recyclables.objects.recyclables_app_generate_offers()
        return self.queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.filterset_class:
            return self.filterset_class(self.request.GET, queryset=queryset).qs
        return queryset

    @action(methods=["get"], detail=False)
    def generate_offers(self, request):
        recyclables = self.filter_queryset(self.get_queryset())

        recyclables_for_buying = recyclables.filter(applications__deal_type=DealType.BUY)

        period = validate_period(request.query_params.get("period", "all"))
        serializer_context = self.get_serializer_context()
        serializer_context["lower_date_bound"] = get_lower_date_bound(period)

        category = request.query_params.get("category")
        serializer_context["category"] = category
        serializer = RecyclablesSerializer(recyclables, many=True, context=serializer_context)

        response = []
        # Добавил
        for i in range(len(recyclables)):
            serializer.data[i]['buyer'] = False
            for j in range(len(recyclables_for_buying)):
                if recyclables[i].id == recyclables_for_buying[j].id:
                    serializer.data[i]['buyer'] = True
        # ______________________________________________
        for i in range(len(serializer.data)):
            # serializer.data[i]['companies_count'] = int(recyclables[i].companies_count)
            serializer.data[i]['companies_buy_app_count'] = int(recyclables[i].companies_buy_app_count)
            #if int(recyclables[i].companies_buy_app_count) > 0:
            #    serializer.data[i]['companies_buy_app_count'] = int(recyclables[i].companies_buy_app_count) - 1
            #else:
            #    serializer.data[i]['companies_buy_app_count'] = 0
            response.append(serializer.data[i])
        return Response(response)


class EquipmentCategoryViewSet(
    BaseQuerySetMixin,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    viewsets.GenericViewSet,
):
    queryset = EquipmentCategory.objects.root_nodes().prefetch_related(
        "equipments"
    )
    serializer_class = EquipmentCategorySerializer
    permission_classes = (AllowAny,)
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )
    search_fields = ("name",)
    ordering_fields = "__all__"


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("name",)
    ordering_fields = "__all__"


class RecyclingCodeViewSet(
    BaseQuerySetMixin,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    viewsets.GenericViewSet,
):
    queryset = RecyclingCode.objects.all()
    # serializer_class = RecyclingCodeSerializer
    permission_classes = (AllowAny,)
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
    )
    search_fields = ("name", "gost_name")
    ordering_fields = "__all__"
