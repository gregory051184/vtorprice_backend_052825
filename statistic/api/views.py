from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.serializers import EmptySerializer
from company.models import Company, RecyclingCollectionType
from exchange.api.views import (
    RecyclablesApplicationFilterSet,
    RecyclablesDealFilterSet,
)
from exchange.models import RecyclablesApplication, RecyclablesDeal, DealStatus
from exchange.utils import (
    validate_period,
    get_truncation_class,
    get_lower_date_bound,
)
from product.api.views import RecyclablesFilterSet, ApplicationsRecyclablesFilterSet
from product.models import Recyclables
from statistic.api.models import (
    RecyclingColTypeWithCount,
    RecyclablesTotalWeightByCategory,
    TotalResponse,
    GraphPoint,
    Graph,
    TotalCompanies,
    TotalEmployees,
    ExchangeVolume,
)
from statistic.api.serializers import RecyclablesStatisticsSerializer, RecyclablesAppStatisticsSerializer, \
    MainPageRecyclableSerializer, ShortRecyclablesAppStatisticsSerializer
from user.api.serializers import UserSerializer
from user.models import UserRole
from drf_yasg import openapi as api


class StatisticsViewSet(GenericViewSet):
    filter_backends = (
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    )
    serializer_class = EmptySerializer

    RECYCLABLES_ACTION = (
        "total_applications",
        "recyclables_volume",
        "exchange_volume"

    )

    @property
    def search_fields(self):
        if self.action == "all_users":
            return ["first_name", "last_name", "phone", "email"]

    @property
    def ordering_fields(self):
        if self.action == "all_users":
            return ["id", "last_name", "company__name"]

    # Data methods
    # В зависимости от метода(self.action - определяет используемый метод) возвращает
    # определённый класс фильтров
    @property
    def filterset_class(self):
        # self.action - равняется названию метода данного класса, который используется
        if self.action in self.RECYCLABLES_ACTION:
            return RecyclablesApplicationFilterSet
        if self.action == "total_deals":
            return RecyclablesDealFilterSet
        if self.action == "recyclables_price":
            return RecyclablesFilterSet
        if self.action == "recyclables_applications_price":
            return ApplicationsRecyclablesFilterSet
        if self.action == "short_recyclables_applications_price":
            return ApplicationsRecyclablesFilterSet

        return FilterSet

    def get_queryset(self):
        if self.action in self.RECYCLABLES_ACTION:
            return RecyclablesApplication.objects.all()

        if self.action == "total_companies":
            return Company.objects.all()

        if self.action == "total_deals":
            return RecyclablesDeal.objects.all()

        if self.action in ["total_employee", "all_users"]:
            User = get_user_model()
            return User.objects.all()

        if self.action == "recyclables_price":
            return Recyclables.objects.annotate_applications()

        if self.action == "recyclables_applications_price":
            return Recyclables.objects.annotate_applications()

        if self.action == "short_recyclables_applications_price":
            return Recyclables.objects.annotate_applications()

        if self.action == "main_page_statistics":
            return Recyclables.objects.annotate_applications()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.filterset_class:
            return self.filterset_class(self.request.GET, queryset=queryset).qs
        return queryset

    # utlis
    @staticmethod
    def _get_count_graph_data(
            TruncClass, qs, field_to_truncate='created_at'  # "delivery_date"
    ) -> list[dict]:
        truncated_applications = qs.annotate(
            truncated_date=TruncClass(field_to_truncate)
        ).order_by("truncated_date", f"-{field_to_truncate}")
        with_count = (
            truncated_applications.values("truncated_date")
            .annotate(count=Count("id"))
            .order_by("truncated_date")
        )
        graph_data = with_count.values_list("count", "truncated_date")
        graph_data = [
            GraphPoint(value=item[0], date=item[1]).dict()
            for item in graph_data
        ]
        return graph_data

    # Actions
    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить статистику(week/month/year/all)",
            )
        ]
    )
    @action(methods=["get"], detail=False)
    def recyclables_price(self, request):
        recyclables = self.filter_queryset(self.get_queryset())
        period = validate_period(request.query_params.get("period", "all"))
        serializer_context = self.get_serializer_context()
        serializer_context["lower_date_bound"] = get_lower_date_bound(period)
        data = RecyclablesStatisticsSerializer(
            recyclables, many=True, context=serializer_context
        )
        return Response(data.data)

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить статистику(week/month/year/all)",
            )
        ]
    )
    @action(methods=["get"], detail=False)
    def short_recyclables_applications_price(self, request):
        recyclables = self.filter_queryset(self.get_queryset().prefetch_related('category'))
        period = validate_period(request.query_params.get("period", "all"))
        get_truncation_class(period)
        serializer_context = self.get_serializer_context()
        serializer_context["lower_date_bound"] = get_lower_date_bound(period)
        if (request.query_params.get("deal_type")):
            deal_type = request.query_params.get("deal_type")
            serializer_context["deal_type"] = deal_type

            data = ShortRecyclablesAppStatisticsSerializer(
                recyclables, many=True, context=serializer_context
            )
            return Response(data.data)
        else:
            data = ShortRecyclablesAppStatisticsSerializer(recyclables, many=True)
            return Response(data.data)

    # ДОБАВИЛ ДЛЯ СТАТИСТИКИ ТЕКУЩИХ ЗАЯВОК И ЦЕН
    @action(methods=["get"], detail=False)
    def recyclables_applications_price(self, request):
        recyclables = self.filter_queryset(
            self.get_queryset())
        period = validate_period(request.query_params.get("period", "all"))

        TruncClass = get_truncation_class(period)
        graph_points = self._get_count_graph_data(TruncClass, recyclables, "created_at")
        graph_data = Graph(points=graph_points)
        total = recyclables.count()

        serializer_context = self.get_serializer_context()
        serializer_context["lower_date_bound"] = get_lower_date_bound(period)
        response = []
        # ДОБАВИЛ ДЛЯ РАЗДЕЛЕНИЯ ПОКУПКА/ПРОДАЖА
        if (request.query_params.get("deal_type")):
            deal_type = request.query_params.get("deal_type")
            serializer_context["deal_type"] = deal_type

            data = RecyclablesAppStatisticsSerializer(
                recyclables, many=True, context=serializer_context
            )
            for i in data.data:
                i['total'] = total
                i['graph'] = graph_data.dict()
                i['deal_type'] = int(deal_type)
                response.append(i)
            return Response(response)
        else:
            data = RecyclablesAppStatisticsSerializer(recyclables, many=True)

            for i in data.data:
                i['total'] = total
                i['graph'] = graph_data.dict()
                response.append(i)
            return Response(response)

    # ендпоинт статистики для главной странице
    @action(methods=["get"], detail=False)
    def main_page_statistics(self, request):

        recyclables = self.filter_queryset(self.get_queryset())
        period = validate_period(request.query_params.get("period", "all"))

        # TruncClass = get_truncation_class(period)
        # graph_points = self._get_count_graph_data(TruncClass, recyclables, "created_at")
        serializer_context = self.get_serializer_context()
        serializer_context["lower_date_bound"] = get_lower_date_bound(period)

        data = MainPageRecyclableSerializer(recyclables, many=True, context=serializer_context)

        return Response(data.data)

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить статистику(week/month/year/all)",
            )
        ]
    )
    @action(methods=["get"], detail=False)
    def recyclables_volume(self, request):
        period = validate_period(request.query_params.get("period", "all"))
        qs = self.filter_queryset(self.get_queryset())

        get_truncation_class(period)
        lower_date_bound = get_lower_date_bound(period)

        if lower_date_bound:
            qs = qs.filter(created_at__gte=lower_date_bound)
        qs = qs.annotate_total_weight()

        aggregated_total_weight = (
            qs.values("recyclables__name")
            .annotate(total_weight_sum=Sum("total_weight"))
            .order_by("recyclables__name")
        )

        to_return = [
            RecyclablesTotalWeightByCategory(
                recyclables=item["recyclables__name"],
                total_weight_sum=float(item["total_weight_sum"]),
            ).dict()
            for item in aggregated_total_weight
        ]

        return Response(to_return)

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить статистику(week/month/year/all)",
            )
        ]
    )
    @action(methods=["get"], detail=False)
    def total_applications(self, request):
        qs = self.filter_queryset(self.get_queryset())

        period = validate_period(request.query_params.get("period", "all"))
        lower_bound = get_lower_date_bound(period)
        TruncClass = get_truncation_class(period)

        if lower_bound:
            qs = qs.filter(created_at__gte=lower_bound)

        graph_points = self._get_count_graph_data(TruncClass, qs, "created_at")
        graph_data = Graph(points=graph_points)
        total = qs.count()
        return Response(TotalResponse(total=total, graph=graph_data).dict())

    @action(detail=False, methods=["get"])
    def total_companies(self, request):
        company_qs = self.get_queryset()

        total = company_qs.count()
        annotated_types = RecyclingCollectionType.objects.annotate(
            company_count=Count("companyactivitytype")
        )

        recycling_data = annotated_types.values_list(
            "name", "company_count", "activity", "color",
        )

        recycling_count: list[dict] = [
            RecyclingColTypeWithCount(
                name=item[0],
                company_count=item[1],
                activity_type=item[2],
                color=item[3],
            ).dict()
            for item in recycling_data
        ]
        response = TotalCompanies(total=total, recycling_count=recycling_count)

        return Response(response.dict())

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить статистику(week/month/year/all)",
            )
        ]
    )
    @action(methods=["get"], detail=False)
    def total_deals(self, request):
        period = validate_period(request.query_params.get("period", "all"))

        qs = self.filter_queryset(self.get_queryset())

        TruncClass = get_truncation_class(period)

        lower_date_bound = get_lower_date_bound(period)

        qs = qs.filter(
            status__in=(
                DealStatus.COMPLETED,
                DealStatus.UNLOADING,
                DealStatus.ACCEPTANCE,
            )
        )

        if lower_date_bound:
            qs = qs.filter(created_at__gte=lower_date_bound)

        graph_data = self._get_count_graph_data(TruncClass, qs)
        total = qs.count()
        response = TotalResponse(graph=Graph(points=graph_data), total=total)
        return Response(response.dict())

    @action(detail=False, methods=["get"])
    def total_employee(self, request):
        users_qs = self.get_queryset()

        logists_count = users_qs.filter(role=UserRole.LOGIST).count()
        managers_count = users_qs.filter(role=UserRole.MANAGER).count()
        admins_count = users_qs.filter(role=UserRole.ADMIN).count()
        users_count = users_qs.filter(role=UserRole.COMPANY_ADMIN).count()

        total = users_qs.count()

        response = TotalEmployees(
            total=total,
            logists=logists_count,
            managers=managers_count,
            admins=admins_count,
            users=users_count,
        )

        return Response(response.dict())

    @action(detail=False, methods=["get"])
    def all_users(self, request):
        qs = self.get_queryset().order_by("-created_at")

        qs = self.filter_queryset(qs)
        paginator_class = self.pagination_class()
        paginated_queryset = paginator_class.paginate_queryset(
            qs, request, view=self
        )
        response = paginator_class.get_paginated_response(
            UserSerializer(
                paginated_queryset,
                many=True,
                fields=[
                    "first_name",
                    "last_name",
                    "id",
                    "email",
                    "role",
                    "company",
                ],
            ).data
        )
        return response

    @action(detail=False, methods=["get"])
    def exchange_volume(self, request):
        qs = self.get_queryset()
        total_price = sum(list(map(lambda x: x.total_price, qs)))
        response_data = ExchangeVolume(total=total_price)

        return Response(response_data.dict())
