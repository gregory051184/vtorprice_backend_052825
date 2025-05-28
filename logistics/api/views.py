# Create your views here.
import datetime
from typing import Callable, Optional, Tuple, Union

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, QuerySet, Model
from django.db.models import Q, Count
from django_filters import MultipleChoiceFilter
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, generics, status
from djangorestframework_camel_case.parser import (
    CamelCaseMultiPartParser,
    CamelCaseFormParser,
)
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_nested.viewsets import NestedViewSetMixin

from common.serializers import EmptySerializer
from common.views import MultiSerializerMixin, DocumentsMixin
from company.models import City, Region
from document_generator.api.serializers import GeneratedDocumentSerializer
from document_generator.common import get_or_generate_document
from document_generator.generators.document_generators import (
    UnloadingAgreement,
    AgreementApplication,
    UniformTransferDocument,
    Waybill,
)
from document_generator.models import (
    GeneratedDocumentType,
)
from exchange.utils import (
    validate_period,
    get_truncation_class,
    get_lower_date_bound,
)
from logistics.api.permisssions import (
    ContragentsAccessPermissions,
    LogisticsOffersPermission,
)
from logistics.api.serializers import (
    CreateContractorSerializer,
    ContractorSerializer,
    CreateTransportApplicationSerializer,
    TransportApplicationSerializer,
    CreateLogisticsOfferSerializer,
    LogisticsOfferSerializer,
    UpdateLogisticsOffer,
    UpdateTransportApplicationSerializer,
)
from logistics.models import (
    Contractor,
    TransportApplication,
    LogisticsOffer,
    TransportApplicationStatus,
)
from user.models import UserRole
from drf_yasg import openapi as api


class ContractorsViewSet(
    DocumentsMixin, MultiSerializerMixin, viewsets.ModelViewSet
):
    permission_classes = [IsAuthenticated, ContragentsAccessPermissions]
    queryset = Contractor.objects.select_related(
        "city", "created_by"
    ).prefetch_related("documents")
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
    )
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]

    search_fields = ("name",)
    filterset_fields = ("city",)
    ordering_fields = "__all__"

    serializer_classes = {
        "create": CreateContractorSerializer,
        "update": CreateContractorSerializer,
    }
    default_serializer_class = ContractorSerializer

    def create(self, request, *args, **kwargs):
        #if len(request.data['documents']) > 0:
        #    docs = request.data['documents']
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_anonymous:
            # Need to check if user is anonymous and return empty queryset
            # Because if we will try to access anonymous user company
            # drf_yasg will throw exception, and there would be no city filtering field
            return queryset.none()
        return queryset.filter(created_by__company=self.request.user.company)


class TransportApplicationFilterSet(FilterSet):
    status = MultipleChoiceFilter(choices=TransportApplicationStatus.choices)

    class Meta:
        model = TransportApplication
        fields = {
            "created_at": ["gte", "lte"],
            "status": ["exact"],
            "shipping_city": ["exact"],
            "delivery_city": ["exact"],
            "created_by": ["exact"],
            "approved_logistics_offer__amount": ["gte", "lte"],
        }


class TransportApplicationFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        user = request.user
        if user.is_anonymous:
            return queryset.none()
        if user.role == UserRole.LOGIST:
            # Annotate with custom status for logist
            queryset = queryset.annotate_logist_status(user)
            logist_status_filter: list = request.query_params.getlist(
                "logistStatus", None
            )
            if not logist_status_filter:
                return queryset

            try:
                logist_status_filter = list(map(int, logist_status_filter))
            except ValueError:
                return queryset.none()

            if logist_status_filter:
                return queryset.filter(logist_status__in=logist_status_filter)
            else:
                return queryset.none()

        if user.role == UserRole.MANAGER:
            return queryset.filter(
                Q(created_by__company__manager=user) | Q(created_by=user)
            )

        if user.role == UserRole.COMPANY_ADMIN:
            return queryset.filter(
                Q(created_by=user) | Q(created_by__company=user.company)
            )

        return queryset


class TransportApplicationViewSet(
    DocumentsMixin, MultiSerializerMixin, viewsets.ModelViewSet
):
    queryset = TransportApplication.objects.select_related(
        "shipping_city", "delivery_city", "created_by"
    )
    serializer_classes = {
        "list": TransportApplicationSerializer,
        "retrieve": TransportApplicationSerializer,
        "create": CreateTransportApplicationSerializer,
    }
    default_serializer_class = UpdateTransportApplicationSerializer
    filter_backends = (
        filters.SearchFilter,
        DjangoFilterBackend,
        TransportApplicationFilterBackend,
    )
    search_fields = ("sender", "recipient", "cargo_type")
    filterset_class = TransportApplicationFilterSet

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "logistStatus",
                api.IN_QUERY,
                type=api.TYPE_ARRAY,
                items=api.Items(api.TYPE_INTEGER),
                required=False,
                description="ID статуса заявки для логиста",
            )
        ]
    )
    # УДАЛИТЬ ОБЯЗАТЕЛЬНО
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """
        Overwritten to support queryparam that can't be placed to FilterSet
        """
        return super().list(request, *args, **kwargs)

    @action(
        detail=True,
        methods=["get"],
        description="Получение договора на отгрузку",
    )
    def unloading_agreement(self, request, pk=None):
        application = self.get_object()
        content_type = ContentType.objects.get_for_model(application)
        generator = UnloadingAgreement(application)
        filter_kwargs = {
            "content_type": content_type,
            "type": GeneratedDocumentType.UNLOADING_AGREMEENT,
            "object_id": application.id,
        }

        document = get_or_generate_document(generator, filter_kwargs)
        return Response(GeneratedDocumentSerializer(document).data)

    @action(
        detail=True, methods=["get"], description='Получение "Договор заявка"'
    )
    def get_application_agreement(self, request, pk=None):
        application = self.get_object()
        content_type = ContentType.objects.get_for_model(application)
        generator = AgreementApplication(application)
        filter_kwargs = {
            "content_type": content_type,
            "type": GeneratedDocumentType.AGREEMENT_APPLICATION,
            "object_id": application.id,
        }
        document = get_or_generate_document(generator, filter_kwargs)
        return Response(GeneratedDocumentSerializer(document).data)

    @action(detail=True, methods=["get"], description="Получение УПД")
    def get_uniform_transfer_document(self, request, pk=None):
        application = self.get_object()
        content_type = ContentType.objects.get_for_model(application)

        generator = UniformTransferDocument(application)
        filter_kwargs = {
            "content_type": content_type,
            "type": GeneratedDocumentType.UNIFORM_TRANSPORTATION_DOCUMENT,
            "object_id": application.id,
        }
        document = get_or_generate_document(generator, filter_kwargs)
        return Response(GeneratedDocumentSerializer(document).data)

    @action(detail=True, methods=["get"], description="ТТН")
    def get_waybill(self, request, pk=None):
        application = self.get_object()
        content_type = ContentType.objects.get_for_model(application)
        generator = Waybill(application)
        filter_kwargs = {
            "content_type": content_type,
            "type": GeneratedDocumentType.WAYBILL,
            "object_id": application.id,
        }
        document = get_or_generate_document(generator, filter_kwargs)
        return Response(GeneratedDocumentSerializer(document).data)


class LogisticsOfferFilterSet(FilterSet):
    class Meta:
        model = LogisticsOffer
        fields = {
            "created_at": ["gte", "lte"],
            "status": ["exact"],
            "amount": ["gte", "lte"],
            "contractor": ["exact"],
            "shipping_date": ["gte", "lte"],
            "logist": ["exact"],
        }


class LogisticsOffersViewSet(
    NestedViewSetMixin,
    MultiSerializerMixin,
    GenericViewSet,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    generics.CreateAPIView,
    generics.UpdateAPIView,
):
    parent_lookup_kwargs = {"transport_application_pk": "application__id"}
    queryset = LogisticsOffer.objects.select_related(
        "logist", "contractor"
    ).prefetch_related("application")
    serializer_classes = {
        "create": CreateLogisticsOfferSerializer,
        "list": LogisticsOfferSerializer,
        "retrieve": LogisticsOfferSerializer,
    }
    default_serializer_class = UpdateLogisticsOffer
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    filterset_class = LogisticsOfferFilterSet

    permission_classes = [LogisticsOffersPermission]


class AnalyticsViewSet(GenericViewSet):
    queryset = TransportApplication.objects.get_completed().select_related(
        "shipping_city", "delivery_city"
    )

    serializer_class = EmptySerializer

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            api.Parameter(
                "shipping_city",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                description="ID города отправления",
                required=True,
            ),
            api.Parameter(
                "delivery_city",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                description="ID города доставки",
                required=True,
            ),
        ],
    )
    @action(methods=["GET"], detail=False)
    def average_price(self, request):
        city_qs = City.objects.all()

        shipping_city, delivery_city = self.__validate_cities_pk(
            request.query_params.get("shipping_city"),
            request.query_params.get("delivery_city"),
        )

        shipping_city, delivery_city = get_object_or_404(
            city_qs, pk=shipping_city
        ), get_object_or_404(city_qs, pk=delivery_city)

        applications = self.get_queryset().filter(
            shipping_city=shipping_city, delivery_city=delivery_city
        )
        average_price = applications.get_average_delivery_price() or 0.0
        return Response({"average_price": average_price})

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить график(week/month/year/all)",
            ),
            api.Parameter(
                "city",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
                description="Город, по котрому строить график",
            ),
            api.Parameter(
                "region",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
                description="Регион, по котрому строить график",
            ),
        ],
    )
    @action(methods=["GET"], detail=False)
    def logistics_deals_amount(self, request):
        period = validate_period(request.query_params.get("period", "all"))

        city_pk = request.query_params.get("city", None)
        region_pk = request.query_params.get("region", None)
        city, region = self._get_city_and_region(city_pk, region_pk)

        TruncClass = get_truncation_class(period)
        lower_date_bound = get_lower_date_bound(period)

        location_filter_func, location = self._get_location_filter_func(
            city, region
        )

        applications = self._get_filtered_applications(
            location, lower_date_bound, location_filter_func
        )
        total_sum = applications.get_total_delivery_sum()
        total_weight = applications.get_total_weight()
        total_count = applications.count()

        graph_data = self._get_graph_data(TruncClass, applications)

        return Response(
            {
                "total_sum": total_sum,
                "total_weight": total_weight,
                "total_count": total_count,
                "graph_data": graph_data,
            }
        )

    def _get_city_and_region(self, city_pk, region_pk):
        if city_pk:
            city_pk = self.__validate_cities_pk(city_pk)[0]
            city = get_object_or_404(City, pk=city_pk)
        else:
            city = None
        if region_pk:
            region_pk = self.__validate_cities_pk(region_pk)[0]
            region = get_object_or_404(Region, pk=region_pk)
        else:
            region = None
        return city, region

    @staticmethod
    def __validate_cities_pk(*args):
        if not all([lambda x: x.isdigit() for x in args]):
            raise ValidationError("ID городов должны быть числами")
        return list(map(int, args))

    @staticmethod
    def _get_graph_data(TruncClass, applications):
        truncated_applications = applications.annotate(
            truncated_date=TruncClass("deals__delivery_date")
        ).order_by("truncated_date", "-created_at")
        with_count = (
            truncated_applications.values("truncated_date")
            .annotate(count=Count("id"))
            .order_by("truncated_date")
        )
        graph_data = with_count.values_list("count", "truncated_date")
        return graph_data

    # TODO: посмотреть как красиво выделить в filterset class
    @classmethod
    def _filter_by_city(cls, qs: QuerySet, city: City) -> QuerySet:
        return qs.filter(Q(delivery_city=city) | Q(shipping_city=city))

    @classmethod
    def _filter_by_region(cls, qs: QuerySet, region: Region) -> QuerySet:
        return qs.filter(
            Q(delivery_city__region=region) | Q(shipping_city__region=region)
        )

    def _get_location_filter_func(
        self, city: City, region: Region
    ) -> Tuple[Optional[Callable], Optional[Union[City, Region]]]:
        if city:
            return self._filter_by_city, city
        if region:
            return self._filter_by_region, region
        return None, None

    def _get_filtered_applications(
        self,
        location: Union[City, Region],
        lower_date_bound: datetime.datetime,
        location_filter: Callable[[QuerySet, Model], QuerySet],
    ):
        """
        :param location: City or District instance, we will use for filtering
        :param lower_date_bound: datetime, lower bound for filtering
        :param location_filter: callable(filter by city or by district), that will be used for filtering.
        """

        additional_filters = {}
        if lower_date_bound:
            additional_filters["deals__delivery_date__gte"] = lower_date_bound

        applications = self.get_queryset().filter(**additional_filters)

        if location and location_filter:
            applications = location_filter(applications, location)
        return applications
