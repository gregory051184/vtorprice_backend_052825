import http
import json
from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django_filters import (
    MultipleChoiceFilter,
    NumberFilter,
    ModelMultipleChoiceFilter,
    BooleanFilter,
)
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from djangorestframework_camel_case.parser import (
    CamelCaseFormParser,
    CamelCaseMultiPartParser,
)

from rest_framework import filters, generics, viewsets, status
from drf_yasg import openapi as api
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated
from rest_framework.mixins import ListModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework_nested.viewsets import NestedViewSetMixin

from chat.models import Chat
from common.filters import FavoriteFilterBackend
from common.subscribe_services.create_payment import create_payment_for_special_app
from common.subscribe_services.payment_acceptance import payment_acceptance_special_application
from common.utils import generate_random_sequence
from common.views import (
    MultiSerializerMixin,
    ImagesMixin,
    FavoritableMixin,
    DocumentsMixin,
    ExcludeMixin, RecyclableApplicationsQuerySetMixin,
)
from company.models import Company, CompanyActivityType, City
from document_generator.api.serializers import GeneratedDocumentSerializer
from document_generator.common import get_or_generate_document
from document_generator.generators.document_generators import (
    AgreementSpecification,
    Act,
)
from document_generator.models import (
    GeneratedDocumentType,
)
from exchange.api.serializers import (
    CreateRecyclablesApplicationSerializer,
    RecyclablesApplicationSerializer,
    ExchangeRecyclablesSerializer,
    RecyclablesDealSerializer,
    CreateRecyclablesDealSerializer,
    CreateReviewSerializer,
    CreateEquipmentApplicationSerializer,
    EquipmentApplicationSerializer,
    EquipmentDealSerializer,
    CreateEquipmentDealSerializer,
    UpdateRecyclablesDealSerializer,
    UpdateEquipmentDealSerializer,
    MatchingApplicationSerializer,
    UpdateRecyclablesApplicationSerializer, RecyclablesDealsForOffers, ApplicationOffersSerializer,
    SpecialApplicationsSerializer, SpecialSerializer, AllRecyclablesApplicationsSerializer,
)
from exchange.models import (
    RecyclablesApplication,
    ApplicationStatus,
    RecyclablesDeal,
    DealStatus,
    Review,
    EquipmentApplication,
    EquipmentDeal, DealType, UrgencyType, SpecialApps, SpecialApplication, SpecialApplicationPaidPeriod,
)
from exchange.services import filter_qs_by_coordinates
from exchange.utils import (
    validate_period,
    get_truncation_class,
    get_lower_date_bound,
)
from exchange.signals import (
    recyclables_deal_status_changed,
    equipment_deal_status_changed,
)
from product.models import Recyclables, Equipment, EquipmentCategory
from statistic.api.serializers import RecyclablesAppStatisticsSerializer
from user.models import UserRole


class DealDocumentGeneratorMixin:
    @action(
        methods=["GET"],
        detail=True,
        description='Получение "Договор-приложение спецификация"',
    )
    def get_specification_agreement(self, request, pk):
        deal = self.get_object()
        content_type = ContentType.objects.get_for_model(deal)

        generator = AgreementSpecification(deal)
        filter_kwargs = {
            "content_type": content_type,
            "object_id": deal.id,
            "type": GeneratedDocumentType.AGREEMENT_SPECIFICATION,
        }
        document = get_or_generate_document(generator, filter_kwargs)

        return Response(GeneratedDocumentSerializer(document).data)

    @action(methods=["GET"], detail=True, description="Получение Акта")
    def get_act_document(self, request, pk):
        user = self.request.user
        if user.is_anonymous:
            raise NotAuthenticated
        deal = self.get_object()
        content_type = ContentType.objects.get_for_model(deal)
        generator = Act(company=request.user.company, deal=deal)
        document_type = (
            GeneratedDocumentType.ACT_BUYER
            if deal.buyer_company == user.company
            else GeneratedDocumentType.ACT_SELLER
        )
        document = get_or_generate_document(
            generator=generator,
            document_filter_kwargs={
                "content_type": content_type,
                "object_id": deal.id,
                "type": document_type,
            },
        )
        return Response(GeneratedDocumentSerializer(document).data)


class RecyclablesApplicationFilterSet(FilterSet):
    total_weight__gte = NumberFilter(
        field_name="total_weight", lookup_expr="gte"
    )
    total_weight__lte = NumberFilter(
        field_name="total_weight", lookup_expr="lte"
    )
    status = MultipleChoiceFilter(choices=ApplicationStatus.choices)
    recyclables = ModelMultipleChoiceFilter(queryset=Recyclables.objects.all())

    is_my = BooleanFilter(method="is_my_filter")

    def is_my_filter(self, queryset, value, *args, **kwargs):
        user = self.request.user
        if args[0] and user.is_authenticated:
            if user.role == UserRole.COMPANY_ADMIN:
                queryset = queryset.filter(company=user.company)
            if user.role == UserRole.MANAGER:
                queryset = queryset.filter(company__manager=user)
        return queryset

    class Meta:
        model = RecyclablesApplication
        fields = {
            "deal_type": ["exact"],
            "urgency_type": ["exact"],
            "recyclables": ["exact"],
            "recyclables__category": ["exact"],
            "city": ["exact"],
            "company": ["exact"],
            "created_at": ["gte", "lte"],
            "price": ["gte", "lte"],
            "application_recyclable_status": ["exact"],
            "city__region": ["exact"],
            "city__region__district": ["exact"],

            # "moisture": ["gte", "lte"],
            # "weediness": ["gte", "lte"],
            "with_nds": ["exact"],
            "bale_weight": ["gte", "lte"],

        }


class AllRecyclablesApplicationsViewSet(
    ImagesMixin,
    MultiSerializerMixin,
    FavoritableMixin,
    ExcludeMixin,
    viewsets.ModelViewSet
):
    queryset = RecyclablesApplication.objects.prefetch_related("company", "recyclables", "company__city",
                                                               "recyclables__category").annotate_total_weight()
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    parent_lookup_kwargs = "company_pk"
    search_fields = ("company__name", "company__inn", "recyclables__name")
    ordering_fields = "__all__"
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
        FavoriteFilterBackend,
    )
    filterset_class = RecyclablesApplicationFilterSet
    serializer_classes = {
        "list": AllRecyclablesApplicationsSerializer
    }

    # pagination_class = None

    def list(self, request, *args, **kwargs):
        period = validate_period(request.query_params.get("period", "all"))
        get_truncation_class(period)
        lower_date_bound = get_lower_date_bound(period)
        queryset = self.filter_queryset(self.get_queryset())
        if lower_date_bound:
            queryset = queryset.filter(Q(status__lte=ApplicationStatus.CLOSED),
                                       urgency_type=UrgencyType.SUPPLY_CONTRACT,
                                       created_at__gte=lower_date_bound)
        else:
            queryset = queryset.filter(Q(status__lte=ApplicationStatus.CLOSED),
                                       urgency_type=UrgencyType.SUPPLY_CONTRACT)

        if request.query_params.get('category'):
            queryset = queryset.filter(
                recyclables__category__id=request.query_params.get('category'))

        if request.query_params.get('sub_category'):
            queryset = queryset.filter(
                recyclables__id=request.query_params.get('sub_category'))
        # queryset = queryset.filter(
        # recyclables__category__id=request.query_params.get('category')) if request.query_params.get(
        # 'category') else queryset

        if not request.query_params.get('page'):
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)


class RecyclablesApplicationViewSet(
    ImagesMixin,
    MultiSerializerMixin,
    FavoritableMixin,
    ExcludeMixin,
    viewsets.ModelViewSet,
    RecyclableApplicationsQuerySetMixin
):
    # queryset = RecyclablesApplication.objects.select_related("company", "recyclables").annotate_total_weight()
    queryset = RecyclablesApplication.objects.prefetch_related("company", "recyclables", "images").prefetch_related(
        "company__city", "company__activity_types", "company__activity_types__advantages",
        "company__activity_types__rec_col_types", "company__city__region",
        "company__city__region__district").annotate_total_weight()
    serializer_classes = {
        "list": RecyclablesApplicationSerializer,
        "retrieve": RecyclablesApplicationSerializer,
        "create": CreateRecyclablesApplicationSerializer,
    }
    default_serializer_class = UpdateRecyclablesApplicationSerializer
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    parent_lookup_kwargs = "company_pk"
    search_fields = ("company__name", "company__inn", "recyclables__name")
    ordering_fields = "__all__"
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
        FavoriteFilterBackend,
    )
    filterset_class = RecyclablesApplicationFilterSet

    def get_queryset(self):
        # Добавил фильтр по виду сделки и её завершённости
        if self.request.query_params.get('status') and self.request.query_params.get('status') == '3':
            qs = super().get_queryset().filter(Q(status=ApplicationStatus.CLOSED))
        else:
            # Закомментировал urgency_type=UrgencyType.READY_FOR_SHIPMENT,
            qs = super().get_queryset().filter(~Q(  # urgency_type=UrgencyType.READY_FOR_SHIPMENT,
                status=ApplicationStatus.CLOSED)).filter(~Q(status=
                                                            ApplicationStatus.DECLINED)).filter(
                is_deleted=0) if self.action != "profile_applications" else super().get_queryset()

        # Фильтр для общего веса (заявки)
        if self.request.query_params.get('total_weight__gte') or (
                self.request.query_params.get('total_weight__gte') and self.request.query_params.get(
            'total_weight__lte')):
            if self.request.query_params.get('total_weight__gte'):
                total_weight_gte = self.request.query_params.get('total_weight__gte')
                qs = qs.filter(Q(total_weight__gte=total_weight_gte))

            if self.request.query_params.get('total_weight__gte') and self.request.query_params.get(
                    'total_weight__lte'):
                total_weight_gte = self.request.query_params.get('total_weight__gte')
                total_weight_lte = self.request.query_params.get('total_weight__lte')
                qs = qs.filter(Q(total_weight__gte=total_weight_gte, total_weight__lte=total_weight_lte))

        # Фильтр по доверию к компании (надёжная/ненадёжная) (общий)
        if self.request.query_params.get('companies_trust'):
            companies_trust = int(self.request.query_params.get('companies_trust'))
            qs = qs.filter(Q(company__status=companies_trust))
        return self.split_query_params(qs, self.request.query_params, self.kwargs)

    def update(self, request, *args, **kwargs):
        if len(request.data) == 1 and request.data['status'] == 3:
            item = RecyclablesApplication.objects.get(id=kwargs['pk'])
            item.status = 3
            item.save()
            return Response(status=status.HTTP_200_OK)
        else:
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

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "exclude",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
                description="ID заявки(ок), которую(ые) необходимо исключить",
            ),
            api.Parameter(
                "is_favorite",
                api.IN_QUERY,
                type=api.TYPE_BOOLEAN,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        period = validate_period(request.query_params.get("period", "all"))
        get_truncation_class(period)
        lower_date_bound = get_lower_date_bound(period)
        pages = request.query_params.get('page')
        queryset = self.filter_queryset(self.get_queryset())
        urgency_type = request.query_params.get('urgency_type')

        no_page = request.query_params.get('no_page')
        is_favorite = request.query_params.get('is_favorite')

        if is_favorite == "true":
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)

            return Response(serializer.data)


        # ЭТОТ IF ДЛЯ КАРТОЧКИ НА ФРОНТЕНДЕ ГДЕ ПОКАЗЫВАЮТСЯ ОБЪЯВЛЕНИЯ ПО ПРОДАЖАМ/ПОКУПКАМ /exchange/3?type=2
        if no_page == 'true':
            queryset = queryset.filter(Q(status__lte=ApplicationStatus.CLOSED),
                                       Q(urgency_type=urgency_type))

            serializer = self.get_serializer(queryset, many=True)
            data = {
                "results": serializer.data,
                "count": len(serializer.data)
            }
            return Response(data)

        if lower_date_bound:
            queryset = queryset.filter(Q(status__lte=ApplicationStatus.CLOSED),
                                       urgency_type=urgency_type if urgency_type else UrgencyType.SUPPLY_CONTRACT,
                                       created_at__gte=lower_date_bound)
        else:
            queryset = queryset.filter(Q(status__lte=ApplicationStatus.CLOSED),
                                       Q(urgency_type=urgency_type if urgency_type else UrgencyType.SUPPLY_CONTRACT))

        if request.query_params.get('category'):
            queryset = queryset.filter(
                recyclables__category__id=request.query_params.get('category'))

        if request.query_params.get('sub_category'):
            queryset = queryset.filter(
                recyclables__id=request.query_params.get('sub_category'))
        if not pages and not urgency_type:
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def company_apps(self, request, *args, **kwargs):
        company_id = request.query_params.get('company')
        data = self.list(request, *args, **kwargs)
        apps = RecyclablesApplication.objects.filter(company_id=company_id)
        for i in apps:
            i.total_weight = i.full_weigth
        app_serializer = RecyclablesApplicationSerializer(apps, many=True)

        data.data['results'] = app_serializer.data
        return data

    @action(methods=["GET"], detail=False)
    def profile_applications(self, request, *args, **kwargs):
        company_id = request.query_params.get('company')
        urgency_type = request.query_params.get('urgency_type')
        apps = RecyclablesApplication.objects.filter(company_id=company_id, urgency_type=urgency_type)

        queryset = self.filter_queryset(apps)
        page = self.paginate_queryset(queryset)

        # ata = self.list(request, *args, **kwargs)

        for i in page:  # apps:(
            i.total_weight = i.full_weigth

        # app_serializer = RecyclablesApplicationSerializer(apps, many=True)
        # app_serializer = RecyclablesApplicationSerializer(page, many=True)
        serializer = self.get_serializer(page, many=True)
        # data.data['results'] = serializer.data  # app_serializer.data
        return self.get_paginated_response(serializer.data)  # data

    @swagger_auto_schema(
        methods=["POST"], request_body=MatchingApplicationSerializer
    )
    @action(methods=["POST"], detail=False)
    def match_applications(self, request):
        serializer = MatchingApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deal = serializer.save()

        return Response(RecyclablesDealSerializer(deal).data)

    # УДАЛИТЬ

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    # __________________________________________________________

    @action(methods=["GET"], detail=False)
    def offer(self, request, *args, **kwargs):
        company_id = request.query_params.get('company_id')
        recyclable_id = request.query_params.get('recyclable_id')
        data = self.list(request, *args, **kwargs)

        apps = RecyclablesApplication.objects.filter(~Q(company_id=company_id),
                                                     deal_type=DealType.SELL,
                                                     recyclables=recyclable_id)
        for i in apps:
            i.total_weight = i.full_weigth
        app_serializer = RecyclablesApplicationSerializer(apps, many=True)
        company = Company.objects.get(id=company_id)

        data.data['results'] = app_serializer.data
        for i in data.data['results']:
            i['offer_company_name'] = company.name
            i['offer_company__email'] = company.email if len(company.email) > 0 else ''
            # i['offer_company_phone'] = company.phone if len(company.phone) > 11 else ''
        return data


class EquipmentApplicationFilterSet(FilterSet):
    status = MultipleChoiceFilter(choices=ApplicationStatus.choices)
    equipment = ModelMultipleChoiceFilter(queryset=Equipment.objects.all())

    is_my = BooleanFilter(method="is_my_filter")

    def is_my_filter(self, queryset, value, *args, **kwargs):
        user = self.request.user
        if args[0] and user.is_authenticated:
            if user.role == UserRole.COMPANY_ADMIN:
                queryset = queryset.filter(company=user.company)
            if user.role == UserRole.MANAGER:
                queryset = queryset.filter(company__manager=user)
        return queryset

    class Meta:
        model = EquipmentApplication
        fields = {
            "deal_type": ["exact"],
            "equipment": ["exact"],
            # ИЗМЕНИЛ
            "equipment__category": ["exact"],
            # "equipment_category": ["exact"],
            "city": ["exact"],
            "company": ["exact"],
            "created_at": ["gte", "lte"],
            "price": ["gte", "lte"],
            "count": ["gte", "lte"],
            "manufacture_date": ["gte", "lte"],
        }


class EquipmentApplicationViewSet(
    ImagesMixin,
    MultiSerializerMixin,
    FavoritableMixin,
    ExcludeMixin,
    viewsets.ModelViewSet,
):
    queryset = EquipmentApplication.objects.select_related(
        "company", "equipment"
    )
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    parent_lookup_kwargs = "company_pk"
    search_fields = ("company__name", "company__inn", "equipment__name")
    ordering_fields = "__all__"
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
        FavoriteFilterBackend,
    )
    default_serializer_class = CreateEquipmentApplicationSerializer
    serializer_classes = {
        "list": EquipmentApplicationSerializer,
        "retrieve": EquipmentApplicationSerializer,
    }
    filterset_class = EquipmentApplicationFilterSet

    # ДОБАВИЛ
    def get_queryset(self):
        qs = super().get_queryset().filter(
            ~Q(status=ApplicationStatus.CLOSED)).filter(
            ~Q(status=ApplicationStatus.DECLINED)).filter(
            is_deleted=0) if self.action != 'retrieve' else super().get_queryset()

        # if self.request.query_params.get('price__gte') or (
        #        self.request.query_params.get('price__gte') and self.request.query_params.get('price__lte')):
        #    if self.request.query_params.get('price__gte'):
        #        price_gte = self.request.query_params.get('price__gte')
        #        qs = qs.filter(Q(price__gte=price_gte))

        #    if self.request.query_params.get('price__gte') and self.request.query_params.get('price__lte'):
        #        price_gte = self.request.query_params.get('price__gte')
        #        price_lte = self.request.query_params.get('price__lte')
        #        qs = qs.filter(Q(price__gte=price_gte, price__lte=price_lte))

        if self.request.query_params.get('was_in_use'):
            was_in_use = int(self.request.query_params.get('was_in_use'))
            if was_in_use == 1:
                qs = qs.filter(Q(was_in_use=0))
            if was_in_use == 2:
                qs = qs.filter(Q(was_in_use=1))

        if self.request.query_params.get('sale_by_part'):
            sale_by_part = int(self.request.query_params.get('sale_by_part'))
            if sale_by_part == 1:
                qs = qs.filter(Q(sale_by_parts=0))
            if sale_by_part == 2:
                qs = qs.filter(Q(sale_by_parts=1))

        if self.request.query_params.get('nds'):
            nds = int(self.request.query_params.get('nds'))
            if nds == 1:
                qs = qs.filter(Q(with_nds=0))
            if nds == 2:
                qs = qs.filter(Q(with_nds=1))

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def profile_applications(self, request, *args, **kwargs):
        company_id = request.query_params.get('company')
        apps = EquipmentApplication.objects.filter(company_id=company_id)

        queryset = self.filter_queryset(apps)
        page = self.paginate_queryset(queryset)

        # data = self.list(request, *args, **kwargs)

        # app_serializer = EquipmentApplicationSerializer(apps, many=True)

        serializer = self.get_serializer(page, many=True)

        # data.data['results'] = serializer.data  # app_serializer.data
        return self.get_paginated_response(serializer.data)  # data

    # ______________________________________________________

    def create(self, request, *args, **kwargs):
        equipment_name = request.data['equipment']
        equipment_description = request.data['description']
        equipment_category = EquipmentCategory.objects.get(id=request.data['category'])
        equip = Equipment.objects.create(name=equipment_name, category=equipment_category,
                                         description=equipment_description if len(equipment_description) > 0 else None)
        equip.save()
        data = request.data
        data['equipment'] = equip.id
        data['category'] = equipment_category.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ExchangeRecyclablesViewSet(
    generics.ListAPIView,
    viewsets.GenericViewSet,
):
    queryset = Recyclables.objects.annotate_applications()
    serializer_class = RecyclablesAppStatisticsSerializer  # ExchangeRecyclablesSerializer
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
    )
    ordering_fields = (
        "name",
        "category__name",
    )
    search_fields = ("name",)
    filterset_fields = ("category",)

    def get_queryset(self):

        qs = super().get_queryset()

        page = self.request.query_params.get("page")

        size = self.request.query_params.get("size")

        urgency_type = self.request.query_params.get("urgency_type")

        ordering = self.request.query_params.get("ordering")

        if ordering and page == '1':
            qs = qs.ordering_applications(ordering, urgency_type, page, size)
            return qs

        if urgency_type:
            qs = qs.annotate_applications(urgency_type=int(urgency_type))
            return qs

        return qs

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "urgency_type",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
                description="Срочность",
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить график(week/month/year/all)",
            ),
        ],
    )
    @action(methods=["GET"], detail=True)
    def graph(self, request, pk):
        urgency_type = int(request.query_params.get("urgency_type"))
        period = request.query_params.get("period", "all")
        period = validate_period(period)
        recyclable: Recyclables = self.get_object()
        TruncClass = get_truncation_class(period)
        lower_date_bound = get_lower_date_bound(period)
        # deals = self.get_filtered_deals(
        #     TruncClass, lower_date_bound, recyclable
        # )
        applications = self.get_filtered_applications(TruncClass, lower_date_bound, recyclable, urgency_type)
        # graph_data = deals.values_list("price", "truncated_date")
        graph_data = applications.values_list("price", "truncated_date")
        return Response(graph_data)

    @staticmethod
    def get_filtered_deals(TruncClass, lower_date_bound, recyclable):
        deals_filter = {
            "application__recyclables": recyclable,
            "status": DealStatus.COMPLETED,
        }
        if lower_date_bound:
            deals_filter["created_at__gte"] = lower_date_bound
        filtered_deals = RecyclablesDeal.objects.filter(**deals_filter)
        deals = (
            filtered_deals.annotate(truncated_date=TruncClass("created_at"))
            .order_by("truncated_date", "-created_at")
            .distinct("truncated_date")
        )
        return deals

    @staticmethod
    def get_filtered_applications(TruncClass, lower_date_bound, recyclable, urgency_type):
        applications_filter = {
            "recyclables": recyclable,
            "status": ApplicationStatus.PUBLISHED,
            "urgency_type": urgency_type
        }
        if lower_date_bound:
            applications_filter["created_at__gte"] = lower_date_bound
        filtered_apps = RecyclablesApplication.objects.filter(**applications_filter)
        apps = (
            filtered_apps.annotate(truncated_date=TruncClass("created_at"))
            .order_by("truncated_date", "-created_at"))

        return apps


class RecyclablesDealFilterSet(FilterSet):
    status = MultipleChoiceFilter(choices=DealStatus.choices)
    is_my = BooleanFilter(method="is_my_filter")

    def is_my_filter(self, queryset, value, *args, **kwargs):
        user = self.request.user
        if args[0] and user.is_authenticated:
            if user.role == UserRole.COMPANY_ADMIN:
                queryset = queryset.filter(
                    Q(supplier_company=user.company)
                    | Q(buyer_company=user.company)
                )
            if user.role == UserRole.MANAGER:
                queryset = queryset.filter(
                    Q(supplier_company__manager=user)
                    | Q(buyer_company__manager=user)
                )
        return queryset

    class Meta:
        model = RecyclablesDeal
        fields = {
            "application__recyclables": ["exact"],
            "application__recyclables__category": ["exact"],
            "shipping_city": ["exact"],
            "delivery_city": ["exact"],
            "supplier_company": ["exact"],
            "buyer_company": ["exact"],
            "created_at": ["gte", "lte"],
            "price": ["gte", "lte"],
            "weight": ["gte", "lte"],
        }


class RecyclablesDealViewSet(
    DealDocumentGeneratorMixin,
    DocumentsMixin,
    MultiSerializerMixin,
    viewsets.ModelViewSet,
):
    queryset = RecyclablesDeal.objects.select_related(
        "application",
        "application__recyclables",
        "supplier_company",
        "buyer_company",
    ).prefetch_related("reviews")
    serializer_classes = {
        "list": RecyclablesDealSerializer,
        "retrieve": RecyclablesDealSerializer,
        "create": CreateRecyclablesDealSerializer,
    }
    default_serializer_class = UpdateRecyclablesDealSerializer
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    search_fields = (
        "supplier_company__name",
        "supplier_company__inn",
        "buyer_company__name",
        "buyer_company__inn",
        "application__recyclables__name",
    )
    ordering_fields = "__all__"
    filter_backends = (
        filters.SearchFilter,
        DjangoFilterBackend,
        filters.OrderingFilter,
    )
    filterset_class = RecyclablesDealFilterSet

    def update(self, request, *args, **kwargs):
        """
        Overriding in order to send signal when changing deal status
        """
        instance: RecyclablesDeal = self.get_object()
        old_status = instance.status
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if old_status != instance.status:
            # Passing status as key-word arg because status in instance has int value
            recyclables_deal_status_changed.send_robust(
                RecyclablesDeal,
                instance=instance,
                status=serializer.data.get("status").get("label"),
            )

        return Response(serializer.data)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_anonymous and user.role == UserRole.LOGIST:
            qs = qs.filter(
                transport_applications__approved_logistics_offer__logist=user
            )
        return qs

    def sort_offers(self, companies, ordering=None):
        if ordering:
            if ordering == 'dealsByThisRecyclable':
                sorted_companies = sorted(companies, key=lambda x: x.deals_by_recyclable_for_offers)
                return sorted_companies
            if ordering == '-dealsByThisRecyclable':
                sorted_companies = sorted(companies, key=lambda x: x.deals_by_recyclable_for_offers)
                return list(reversed(sorted_companies))

            if ordering == 'lastDealDate':
                sorted_companies = sorted(companies, key=lambda x: x.last_deal_date)
                return sorted_companies
            if ordering == '-lastDealDate':
                sorted_companies = sorted(companies, key=lambda x: x.last_deal_date)
                return list(reversed(sorted_companies))

            if ordering == 'address':
                sorted_companies = sorted(companies, key=lambda x: x.address)
                return sorted_companies
            if ordering == '-address':
                sorted_companies = sorted(companies, key=lambda x: x.address)
                return list(reversed(sorted_companies))
            if ordering == 'averageReviewRate':
                sorted_companies = sorted(companies, key=lambda x: x.average_review_rate)
                return sorted_companies
            if ordering == '-averageReviewRate':
                sorted_companies = sorted(companies, key=lambda x: x.average_review_rate)
                return list(reversed(sorted_companies))

            if ordering == 'buyAppsByThisRecyclable':
                sorted_companies = sorted(companies, key=lambda x: x.buy_apps_by_recyclable_for_offers)
                return sorted_companies
            if ordering == '-buyAppsByThisRecyclable':
                sorted_companies = sorted(companies, key=lambda x: x.buy_apps_by_recyclable_for_offers)
                return list(reversed(sorted_companies))

            if ordering == 'lastAppDate':
                sorted_companies = sorted(companies, key=lambda x: x.last_buy_app_date)
                return sorted_companies
            if ordering == '-lastAppDate':
                sorted_companies = sorted(companies, key=lambda x: x.last_buy_app_date)
                return list(reversed(sorted_companies))

        return companies

    @action(methods=["get"], detail=True)
    def companies_offers(self, request, pk=None, **kwargs):
        companies = []
        ordering = request.query_params.get('ordering')
        # deals = RecyclablesDeal.objects.filter(application__recyclables=pk)

        # ДОБАВИЛ
        applications_for_sell_count = len(
            RecyclablesApplication.objects.filter(recyclables=pk, deal_type=DealType.SELL))
        applications = RecyclablesApplication.objects.filter(recyclables=pk, deal_type=DealType.BUY)
        for i in applications:
            if i.company not in companies:
                deal_s = RecyclablesDeal.objects.filter(application__recyclables=pk,
                                                        buyer_company_id=i.company.id)
                apps = RecyclablesApplication.objects.filter(company_id=i.company.id, recyclables=pk,
                                                             deal_type=DealType.BUY)
                # recyclable = CompanyRecyclables.objects.filter(id=pk)

                apps_count = len(apps)
                buy_count = len(deal_s)
                if len(apps) > 0:
                    if (len(deal_s) > 0):
                        last_deal_date = deal_s.order_by('-created_at')[0].created_at
                        i.company.last_deal_date = last_deal_date
                    # last_deal_date = len(deal_s) > 0 if deal_s.order_by('-created_at')[0].created_at else ''

                    last_buy_app_date = apps.order_by('-created_at')[0].created_at

                    i.company.deals_by_recyclable_for_offers = buy_count

                    i.company.last_buy_app_date = last_buy_app_date
                    i.company.buy_apps_by_recyclable_for_offers = apps_count

                    i.company.app_offers_count = applications_for_sell_count

                companies.append(i.company)

        # for i in deals:
        #    if i.buyer_company not in companies:
        #        deal_s = RecyclablesDeal.objects.filter(application__recyclables=pk,
        #                                                buyer_company_id=i.buyer_company_id)
        #        buy_count = len(deal_s)
        #        last_deal_date = deal_s.order_by('-created_at')[0].created_at
        #        i.buyer_company.deals_by_recyclable_for_offers = buy_count
        #        i.buyer_company.last_deal_date = last_deal_date
        #        companies.append(i.buyer_company)

        sorted_companies = self.sort_offers(companies, ordering)
        serializer = RecyclablesDealsForOffers(sorted_companies, many=True)
        return Response(serializer.data)


class ReviewViewSet(
    NestedViewSetMixin,
    GenericViewSet,
    generics.CreateAPIView,
    generics.UpdateAPIView,
):
    queryset = Review.objects.all()
    serializer_class = CreateReviewSerializer
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    parent_lookup_kwargs = {"object_pk": "object_id"}


class EquipmentDealFilterSet(FilterSet):
    status = MultipleChoiceFilter(choices=DealStatus.choices)
    is_my = BooleanFilter(method="is_my_filter")

    def is_my_filter(self, queryset, value, *args, **kwargs):
        user = self.request.user
        if args[0] and user.is_authenticated:
            if user.role == UserRole.COMPANY_ADMIN:
                queryset = queryset.filter(
                    Q(supplier_company=user.company)
                    | Q(buyer_company=user.company)
                )
            if user.role == UserRole.MANAGER:
                queryset = queryset.filter(
                    Q(supplier_company__manager=user)
                    | Q(buyer_company__manager=user)
                )
        return queryset

    class Meta:
        model = EquipmentDeal
        fields = {
            "application__equipment": ["exact"],
            # ИЗМЕНИЛ
            "application__equipment__category": ["exact"],
            # "application__category": ["exact"],

            "shipping_city": ["exact"],
            "delivery_city": ["exact"],
            "supplier_company": ["exact"],
            "buyer_company": ["exact"],
            "created_at": ["gte", "lte"],
            "price": ["gte", "lte"],
        }


class EquipmentDealViewSet(
    DealDocumentGeneratorMixin,
    DocumentsMixin,
    MultiSerializerMixin,
    viewsets.ModelViewSet,
):
    queryset = EquipmentDeal.objects.select_related(
        "application",
        "application__equipment",
        "supplier_company",
        "buyer_company",
    ).prefetch_related("reviews")
    serializer_classes = {
        "list": EquipmentDealSerializer,
        "retrieve": EquipmentDealSerializer,
        "create": CreateEquipmentDealSerializer,
    }
    default_serializer_class = UpdateEquipmentDealSerializer
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    search_fields = (
        "supplier_company__name",
        "supplier_company__inn",
        "buyer_company__name",
        "buyer_company__inn",
        "application__equipment__name",
    )
    ordering_fields = "__all__"
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
    )
    filterset_class = EquipmentDealFilterSet

    def update(self, request, *args, **kwargs):
        """
        Overriding in order to send signal when changing deal status
        """

        instance: EquipmentDeal = self.get_object()
        old_status = instance.status
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if old_status != instance.status:
            # Passing status as key-word arg because status in instance has int value
            equipment_deal_status_changed.send_robust(
                EquipmentDeal,
                instance=instance,
                status=serializer.data.get("status").get("label"),
            )

        return Response(serializer.data)


class SpecialViewSet(ImagesMixin, viewsets.ModelViewSet):
    queryset = SpecialApplication.objects.all()
    serializer_class = SpecialSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if request.data['is_deleted']:
            instance.is_deleted = request.data['is_deleted']
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        period = SpecialApplicationPaidPeriod.objects.get(id=int(request.data['period']))
        city = City.objects.get(id=int(request.data['city']))
        spec_number = generate_random_sequence()
        chat = Chat.objects.create(
            name=f"Спец. предложение № {spec_number}"
        )
        special = SpecialApplication.objects.create(
            period=period,
            with_nds=request.data['with_nds'],
            price=request.data['price'],
            address=request.data['address'],
            latitude=request.data['latitude'],
            longitude=request.data['longitude'],
            description=request.data['description'],
            city=city,
            chat=chat,
        )
        # serializer = self.get_serializer(data=request.data)

        # serializer.is_valid(raise_exception=True)
        # serializer.save()
        # super().create(request)

        c = request.data
        c['time_end'] = request.data['time_begin']
        special_application = SpecialApplication.objects.get(id=special.id)
        c['special_application_id'] = special_application.id
        confirmation_url = create_payment_for_special_app(c)
        return Response({'confirmation_url': confirmation_url, 'id': special_application.id},
                        200)  # super().create(request)

    def list(self, request, *args, **kwargs):
        # Закомментил так как выдавало по десять экземпляров на страницу, а здесь страницы не нужны
        # queryset = self.filter_queryset(self.get_queryset())

        # page = self.paginate_queryset(queryset)
        # if page is not None:
        #    serializer = self.get_serializer(page, many=True)
        #    return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(self.queryset, many=True)
        return Response(serializer.data)


class SpecialApplicationsViewSet(
    viewsets.ModelViewSet
):
    queryset = SpecialApps.objects.all()

    serializer_class = SpecialApplicationsSerializer

    def retrieve(self, request, *args, **kwargs):
        company_special_application = SpecialApps.objects.get(~Q(is_deleted=1), id=kwargs['pk'])
        if company_special_application:
            serializer = self.get_serializer(company_special_application)
            return Response(serializer.data)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def list(self, request, *args, **kwargs):
        query = self.get_queryset()
        serializer = self.get_serializer(query, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # @action(methods=["POST"], detail=False)
    # def create_payment(self, request):
    #    #period = request.data['period']['id']
    #    c = request.data
    #    c['time_end'] = request.data['time_begin']
    #    special_application = SpecialApplication.objects.get(period=request.data['period'])
    #    c['special_application_id'] = special_application.id
    #    confirmation_url = create_payment_for_special_app(c)
    #
    #    return Response({'confirmation_url': confirmation_url}, 200)

    @action(methods=["POST"], detail=False)
    def payment_acceptance(self, request):
        response = json.loads(request.data)

        if payment_acceptance_special_application(response):
            Response(200)

        return Response(404)
