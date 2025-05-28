import json
import os
from itertools import chain

import django_filters
from django.db import models
from django.db.models import Count, Q
from django.forms import model_to_dict
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from djangorestframework_camel_case.parser import (
    CamelCaseFormParser,
    CamelCaseMultiPartParser,
)

from django.core.mail import send_mail
from requests import post
from drf_yasg import openapi as api
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.viewsets import GenericViewSet
from rest_framework_nested.viewsets import NestedViewSetMixin
from common.filters import FavoriteFilterBackend
from common.permissions import IsOwner
from common.subscribe_services.create_payment import create_payment
from common.subscribe_services.payment_acceptance import payment_acceptance
from common.utils import (
    get_search_terms_from_request,
    str2bool,
    get_grouped_qs,
    get_nds_tax,
)
from common.views import (
    BulkCreateMixin,
    MultiSerializerMixin,
    CompanyOwnerQuerySetMixin,
    NestedRouteQuerySetMixin,
    FavoritableMixin, CompanyQueryMixin,
)

from company.api.serializers import (
    CompanySerializer,
    CompanyDocumentSerializer,
    CompanyRecyclablesSerializer,
    CompanyAdditionalContactSerializer,
    CompanyVerificationRequestSerializer,
    CreateCompanySerializer,
    CreateCompanyDocumentSerializer,
    CreateCompanyAdditionalContactSerializer,
    CreateCompanyRecyclablesSerializer,
    NonExistCompanySerializer,
    CompanyAdvantageSerializer,
    RecyclingCollectionTypeSerializer,
    CreateCompanyActivityTypeSerializer,
    CompanyActivityTypeSerializer,
    CreateCompanyVerificationRequestSerializer,
    SetOwnerCompanySerializer,
    UpdateCompanyVerificationRequestSerializer,
    ListCompanySerializer,
    CitySerializer,
    RegionSerializer, ProposalSerializer, SubscribeSerializer, SubscribeCompanySerializer, EquipmentProposalSerializer,
    DistrictSerializer, CompaniesListForMainFilterSerializer
)
from company.models import (
    Company,
    CompanyDocument,
    CompanyRecyclables,
    CompanyAdditionalContact,
    CompanyVerificationRequest,
    CompanyAdvantage,
    RecyclingCollectionType,
    CompanyActivityType,
    City,
    CompanyVerificationRequestStatus,
    ActivityType,
    Region, Proposal,
    Subscribe, SubscribesCompanies, EquipmentProposal, District
)
from company.services.company_data.get_data import get_companies
from exchange.api.serializers import DealReviewSerializer
from exchange.models import Review, RecyclablesApplication, RecyclablesDeal, DealStatus, UrgencyType, ApplicationStatus
from user.models import UserRole


class CompanyViewSet(
    CompanyQueryMixin,
    MultiSerializerMixin,
    FavoritableMixin,
    viewsets.ModelViewSet,
):
    queryset = (
        Company.objects.select_related("city")
        .prefetch_related(
            "documents",
            "recyclables",
            "contacts",
            "activity_types",
            "review_set",
            "city__region",
            "city__region__district"
        )
        .annotate(recyclables_count=Count("recyclables"))
        .annotate(monthly_volume=models.Sum("recyclables__monthly_volume"))
    )

    serializer_classes = {
        "list": ListCompanySerializer,
        "set_owner": SetOwnerCompanySerializer,
        "retrieve": CompanySerializer,
    }
    default_serializer_class = CreateCompanySerializer
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
        FavoriteFilterBackend,
    )

    search_fields = ("name", "inn")
    ordering_fields = "__all__"
    filterset_fields = {
        # "activity_types": ["exact"],
        "activity_types__rec_col_types": ["exact"],
        "activity_types__advantages": ["exact"],
        # "recyclables__recyclables": ["exact"],
        "status": ["exact"],
        "city": ["exact"],
        "manager": ["exact"],
        "created_at": ["gte", "lte"],
        "city__region": ["exact"],
        "city__region__district": ["exact"],
        "with_nds": ["exact"],
    }

    def update(self, request, *args, **kwargs):
        company = get_object_or_404(Company, id=int(kwargs['pk']))
        if request.data.get('image') is not None:
            if company.image != '':
                os.remove(os.getcwd() + '/media/' + str(company.image))
        # if company.image != '' and request.data.get('image') is None:
        #    os.remove(os.getcwd() + '/media/' + str(company.image))
        #    company.image = ''
        #    company.save()
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

    def get_queryset(self):
        qs = super().get_queryset()
        if (self.request.query_params.get('activity_types')):
            activity_types = int(self.request.query_params.get('activity_types'))
            qs = qs.filter(activity_types__rec_col_types__companyactivitytype__activity=activity_types)

        # если используются методы put и patch, то queryset меняется
        if self.action in ("put", "patch"):
            # дополнительная фильтрация по владельцу компании(owner)
            if self.request.user.role == UserRole.COMPANY_ADMIN:
                return qs.filter(owner=self.request.user)
                # дополнительная фильтрация по менеджеру(manager)
            elif self.request.user.role == UserRole.MANAGER:
                return qs.filter(manager=self.request.user)
            elif self.request.user.role in (
                    UserRole.ADMIN,
                    UserRole.SUPER_ADMIN,
            ):
                return qs
            else:
                return qs.none()
        return qs

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "global_search",
                api.IN_QUERY,
                type=api.TYPE_BOOLEAN,
                required=False,
                description="Глобальный поиск компаний",
            ),
            api.Parameter(
                "is_favorite",
                api.IN_QUERY,
                type=api.TYPE_BOOLEAN,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """
        Overridden to make serialization work correctly when queryset
        contains a company that does not exist in the database
        """
        queryset = self.filter_queryset(self.get_queryset())

        queryset = self.query_filters(queryset, request.query_params)

        non_exist = False
        # проверяем является ли queryset списком и если да, то ставим в True non_exist
        if isinstance(queryset, list):
            non_exist = True

        page = self.paginate_queryset(queryset)
        if page is not None:
            if non_exist:
                serializer = NonExistCompanySerializer(page, many=True)
            else:
                serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # После регистрации пользователь попадает на страницу
    # регистрации компании где как раз происходит поиск
    # (определение) компании по ИНН
    # Ищет компанию по ИНН или названию, которой нет в БД
    # через сервис dadata,попутно определяет город нахождения
    # и если его нет, то заносит этот город в БД
    # Возвращает список компаний (компанию при регистрации)
    def filter_queryset(self, queryset):
        """
        Overridden to support retrieving a company that is not in the database
        """

        queryset = super().filter_queryset(queryset)

        if self.request.query_params.get('is_jur_or_ip'):

            is_jur_or_ip = int(self.request.query_params.get('is_jur_or_ip'))

            if is_jur_or_ip == 1:
                queryset = queryset.filter(name__icontains="ООО")

            if is_jur_or_ip == 2:
                queryset = queryset.filter(name__icontains="ИП")

        # if self.request.query_params.get('company_failed_deals'):
        #     company_failed_deals = int(self.request.query_params.get('company_failed_deals'))
        #     if company_failed_deals == 2:
        #         apps_ids = RecyclablesDeal.objects.filter(Q(status=DealStatus.PROBLEM)).values_list("application",
        #                                                                                             flat=True)
        #         queryset = queryset.filter(id__in=apps_ids)
        #     if company_failed_deals == 1:
        #         apps_ids = RecyclablesDeal.objects.filter(~Q(status=DealStatus.PROBLEM)).values_list("application",
        #                                                                                              flat=True)
        #         queryset = queryset.filter(id__in=apps_ids)
        #
        # if self.request.query_params.get('company_volume'):
        #
        #     company_volume = int(self.request.query_params.get('company_volume'))
        #
        #     deals = RecyclablesDeal.objects.all()
        #
        #     companies_buy_ids = deals.values_list("buyer_company_id", flat=True)
        #     companies_sell_ids = deals.values_list("supplier_company_id", flat=True)
        #
        #     full_list = list(chain(companies_sell_ids, companies_buy_ids))
        #     current_apps_ids = []
        #     for i in full_list:
        #         deals_sum = 0
        #         lst = []
        #
        #         for j in deals:
        #
        #             if i == j.buyer_company_id:
        #                 deals_sum += j.weight
        #                 lst.append(j.buyer_company_id)
        #                 deals_sum += j.weight
        #             if i == j.supplier_company_id:
        #                 lst.append(j.supplier_company_id)
        #         if deals_sum >= company_volume:
        #             current_apps_ids.extend(lst)
        #
        #     queryset = queryset.filter(id__in=current_apps_ids)

        # возвращает условий поиска в виде списка строк
        search_terms = get_search_terms_from_request(self.request)

        if not search_terms:
            return queryset
        # в данном случае global_search == False, т.к. предаётся со значением false
        global_search = str2bool(
            self.request.query_params.get("global_search", "false")
        )

        if not queryset and global_search:
            query = search_terms[0]
            queryset = get_companies(query)

        return queryset

    # Определяет список прав у пользователей
    def get_permissions(self):
        if self.action == "list":
            permission_classes = [AllowAny]
        else:
            permission_classes = self.permission_classes
        return [permission() for permission in permission_classes]

    # Устанавливает доп url по созданию владельца компании - domain/api/companies/set_owner
    @action(methods=["POST"], detail=True)
    def set_owner(self, request, *args, **kwargs):
        # Если у пользователя есть атрибут "my_company", то он уже является owner какой-то компании
        if hasattr(request.user, "my_company"):
            raise PermissionDenied
        # получаем экземпляр данной компании
        company = self.get_object()
        if company.owner:
            raise ValidationError("Компания уже есть в системе")
        company.owner = request.user
        company.save()
        # change action for correct serialization of object
        self.action = "retrieve"
        return self.retrieve(request, *args, **kwargs)

    # Устанавливает доп url по ставке НДС (показывает ставку) - domain/api/companies/nds_tax
    @action(methods=["GET"], detail=False)
    def nds_tax(self, request, *args, **kwargs):
        return Response(get_nds_tax(), status=status.HTTP_200_OK)

    @action(methods=["GET"], detail=False)
    def companies_with_applications_for_main_filter(self, request, *args, **kwargs):
        filter_query = self.filter_queryset(self.get_queryset().select_related("city")
                                            .prefetch_related(
            "documents",
            "recyclables",
            "contacts",
            "activity_types",
            "review_set",
            "city__region",
            "city__region__district",
        )
                                            .annotate(recyclables_count=Count("recyclables"))
                                            .annotate(monthly_volume=models.Sum("recyclables__monthly_volume")))
        filter_query = self.query_filters(filter_query, request.query_params)
        # filter_query = filter_query.filter(company_recyclables__contains=recyclable)

        # def get_ids_list_for_apps(query):
        #     listed = set()
        #     for i in query:
        #         listed.add(i.company_id)
        #     listed = list(listed)
        #     return listed
        #
        # def get_ids_list(query):
        #     listed = set()
        #     for i in query:
        #         listed.add(i.id)
        #     listed = list(listed)
        #     return listed
        #
        # non_exist = False
        # if isinstance(filter_query, list):
        #     non_exist = True
        #
        # applications = RecyclablesApplication.objects.filter(company_id__in=get_ids_list(filter_query))
        # if self.request.query_params.get('company_has_applications'):
        #     current_apps = int(self.request.query_params.get('company_has_applications'))
        #     if current_apps == 2:
        #         applications = applications.filter(~Q(status=ApplicationStatus.CLOSED),
        #                                            company_id__in=get_ids_list(filter_query))
        #     if current_apps == 1:
        #         applications = applications.filter(Q(status=ApplicationStatus.CLOSED),
        #                                            company_id__in=get_ids_list(filter_query))
        # if self.request.query_params.get('company_has_supply_contract'):
        #     urgency_type = int(self.request.query_params.get('company_has_supply_contract'))
        #     if urgency_type == 2:
        #         applications = applications.filter(Q(urgency_type=UrgencyType.SUPPLY_CONTRACT),
        #                                            company_id__in=get_ids_list(filter_query))
        #     if urgency_type == 1:
        #         applications = applications.filter(~Q(urgency_type=UrgencyType.SUPPLY_CONTRACT),
        #                                            company_id__in=get_ids_list(filter_query))
        #
        # response_companies = Company.objects.filter(id__in=get_ids_list_for_apps(applications))
        non_exist = False
        if isinstance(filter_query, list):
            non_exist = True
        page = self.paginate_queryset(filter_query)
        if non_exist:
            serializer = NonExistCompanySerializer(page, many=True)
        else:
            serializer = CompaniesListForMainFilterSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class CompanySettingsViewMixin:
    # Переопределяет метод get_queryset
    def get_queryset(self):
        qs = super().get_queryset()
        company_pk = self.request.query_params.get("company")
        # Если есть компания
        if company_pk:
            company = get_object_or_404(Company, pk=company_pk)
            # Если данная сущность является типом CompanyAdvantageViewSet
            # (т.е. данный миксин используется в модели CompanyAdvantageViewSet)
            if isinstance(self, CompanyAdvantageViewSet):
                # получаем список id экземпляров модели CompanyAdvantage
                advantages_ids = CompanyActivityType.objects.filter(
                    company=1, advantages__isnull=False
                ).values_list("advantages", flat=True)
                # получаем список экземпляров модели CompanyAdvantage
                qs = CompanyAdvantage.objects.filter(id__in=advantages_ids)
            else:
                # Во всех других случаях фильтруем по компании
                qs = qs.filter(company=company)
        return qs

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "company",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class CompanyDocumentViewSet(
    # CompanyOwnerQuerySetMixin переопределяет queryset на фильтрацию по owner
    CompanyOwnerQuerySetMixin,
    # MultiSerializerMixin даёт возможность использовать несколько классов сериалайзеров
    MultiSerializerMixin,
    # BulkCreateMixin Помогает при создании документов из списка
    BulkCreateMixin,
    viewsets.ModelViewSet,
    # CompanySettingsViewMixin В данном случае queryset фильтруется по компании
    CompanySettingsViewMixin,
):
    queryset = CompanyDocument.objects.all()
    serializer_classes = {"create": CreateCompanyDocumentSerializer}
    default_serializer_class = CompanyDocumentSerializer
    yasg_parser_classes = [CamelCaseFormParser, CamelCaseMultiPartParser]

    def destroy(self, request, *args, **kwargs):
        document_to_delete = get_object_or_404(CompanyDocument, id=int(kwargs['pk']))
        os.remove(os.getcwd() + '/media/' + str(document_to_delete.file))
        return super().destroy(request, *args, **kwargs)


class CompanyRecyclablesViewSet(
    # TODO: NestedRouteQuerySetMixin нужно тестировать, применение не очевидно!
    # В данном случае фильтрация перерабатываемых материалов происходит по id компании
    NestedRouteQuerySetMixin,
    # CompanyOwnerQuerySetMixin переопределяет queryset на фильтрацию по owner
    CompanyOwnerQuerySetMixin,
    # MultiSerializerMixin даёт возможность использовать несколько классов сериалайзеров
    MultiSerializerMixin,
    # BulkCreateMixin Помогает при создании документов из списка
    BulkCreateMixin,
    # CompanySettingsViewMixin В данном случае queryset фильтруется по компании
    CompanySettingsViewMixin,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    generics.CreateAPIView,
    generics.DestroyAPIView,
    viewsets.GenericViewSet,
):
    queryset = CompanyRecyclables.objects.all()
    # Данный класс используется при методе create
    serializer_classes = {"create": CreateCompanyRecyclablesSerializer}
    default_serializer_class = CompanyRecyclablesSerializer
    # Переменные используемая в NestedRouteQuerySetMixin
    create_with_removal = True
    nested_route_lookup_field = "company_pk"

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "company",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
            )
        ]
    )
    # Определяет url адрес для удаления всех материалов переработки у компании
    # domain/api/company_recyclables/delete_all_recyclables
    @action(methods=["DELETE"], detail=False)
    def delete_all_recyclables(self, request):
        user = request.user
        if user.is_anonymous:
            raise PermissionDenied
        company_pk = request.query_params.get("company")
        company = self.request.user.company
        if company_pk:
            company = get_object_or_404(Company.objects.all(), pk=company_pk)

        if user.company != company or user.role == UserRole.LOGIST:
            if not (user.role == UserRole.MANAGER and company.manager == user):
                raise PermissionDenied
        if user.role == UserRole.COMPANY_ADMIN and user.company != company:
            raise PermissionDenied

        company.recyclables.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompanyAdditionalContactViewSet(
    CompanyOwnerQuerySetMixin,
    MultiSerializerMixin,
    BulkCreateMixin,
    viewsets.ModelViewSet,
):
    queryset = CompanyAdditionalContact.objects.all()
    serializer_classes = {"create": CreateCompanyAdditionalContactSerializer}
    default_serializer_class = CompanyAdditionalContactSerializer


class CompanyAdvantageViewSet(generics.ListAPIView, viewsets.GenericViewSet):
    queryset = CompanyAdvantage.objects.all()
    serializer_class = CompanyAdvantageSerializer
    permission_classes = [AllowAny]
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    filterset_fields = ("activity",)
    search_fields = ("name",)


class RecyclingCollectionTypeViewSet(
    generics.ListAPIView,
    viewsets.GenericViewSet,
):
    queryset = RecyclingCollectionType.objects.all()
    serializer_class = RecyclingCollectionTypeSerializer
    permission_classes = [AllowAny]
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    filterset_fields = ("activity",)
    search_fields = ("name",)

    # Определяет url адрес для получения списка видов деятельности
    # domain/api/recycling_collection_types/activity_grouped_list
    @action(methods=["GET"], detail=False)
    def activity_grouped_list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset().order_by("activity"))
        # Группирует объекты qs на основании поля activity
        grouped = get_grouped_qs(qs, "activity")
        result = []
        # создаём объект data на базе сгруппированного списка grouped
        for k, v in grouped.items():
            data = {
                "id": k,
                "label": ActivityType(k).label,
                "rec_col_types": self.get_serializer(v, many=True).data,
            }
            result.append(data)

        return Response(result, status=status.HTTP_200_OK)


class CompanyVerificationRequestFilterBackend(filters.BaseFilterBackend):
    # Фильтрует компании на основании вида деятельности:
    # типов (переработчик, покупатель и т.д.)(CompanyActivityType (activity_types - это ForeignKey на Company))
    #  rec_col_types это ключ ManyToMany на RecyclingCollectionType
    def filter_queryset(self, request, queryset, view):
        coll_type = request.query_params.get("collection_type")
        if coll_type:
            queryset = queryset.filter(
                company__activity_types__rec_col_types=coll_type
            )

        return queryset


class CompanyVerificationFilterSet(FilterSet):
    class Meta:
        model = CompanyVerificationRequest
        fields = {
            "company__recyclables__recyclables": ["exact"],
            "company__recyclables__recyclables__category": ["exact"],
            "company__activity_types__activity": ["exact"],
            "company__city": ["exact"],
            "created_at": ["gte", "lte"],
            "status": ["exact"],
        }


# ViewSet по работе с статусом верификации компании (новая, проверенная, надёжная, отклонённая)
class CompanyVerificationRequestViewSet(
    MultiSerializerMixin,
    generics.RetrieveAPIView,
    generics.ListAPIView,
    generics.UpdateAPIView,
    generics.CreateAPIView,
    viewsets.GenericViewSet,
):
    # Данный запрос возвращает все экземпляры CompanyVerificationRequest со связанными с ними company и user
    queryset = CompanyVerificationRequest.objects.select_related(
        "company", "employee"
    )
    serializer_classes = {
        "create": CreateCompanyVerificationRequestSerializer,
        "list": CompanyVerificationRequestSerializer,
    }
    default_serializer_class = UpdateCompanyVerificationRequestSerializer
    filter_backends = (
        filters.SearchFilter,
        filters.OrderingFilter,
        DjangoFilterBackend,
        CompanyVerificationRequestFilterBackend,
    )
    # Поля, по которым будет происходить поиск
    search_fields = ("company__name", "company__inn")
    # Поля, по которым будет происходить сортировка
    ordering_fields = ("created_at", "company__city__name")
    filterset_class = CompanyVerificationFilterSet

    # Фильтрация происходит на базе CompanyVerificationFilterSet
    # Если запрос на получение списка то почему-то выдаёт только записи со статусом NEW
    def get_queryset(self):
        qs = super().get_queryset()

        if self.action == "list":
            qs = qs.filter(status=CompanyVerificationRequestStatus.NEW)

        return qs

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "collection_type",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


# ViewSet по работе с типом компании (покупатель, переработчик, поставщик)
class CompanyActivityTypeViewSet(
    # TODO: NestedRouteQuerySetMixin нужно тестировать, применение не очевидно!
    # В данном случае фильтрация перерабатываемых материалов происходит по id компании
    NestedRouteQuerySetMixin,
    CompanyOwnerQuerySetMixin,
    MultiSerializerMixin,
    generics.ListAPIView,
    generics.RetrieveAPIView,
    generics.CreateAPIView,
    generics.DestroyAPIView,
    viewsets.GenericViewSet,
):
    queryset = CompanyActivityType.objects.all()
    serializer_classes = {"create": CreateCompanyActivityTypeSerializer}
    default_serializer_class = CompanyActivityTypeSerializer
    nested_route_lookup_field = "company_pk"


class CompanyReviewsViewset(
    NestedViewSetMixin, GenericViewSet, generics.ListAPIView
):
    parent_lookup_kwargs = {"company_pk": "company__pk"}
    queryset = Review.objects.get_queryset()
    serializer_class = DealReviewSerializer


class DistrictViewSet(generics.ListAPIView, viewsets.GenericViewSet):
    queryset = District.objects.all()
    serializer_class = DistrictSerializer
    permission_classes = [AllowAny]
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name",)


class RegionViewSet(generics.ListAPIView, viewsets.GenericViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = [AllowAny]
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name",)


# Фильтрация запроса будет происходить по pk(id) города
class CityFilter(FilterSet):
    region_pk = django_filters.NumberFilter(field_name="region__pk")

    class Meta:
        model = City
        fields = ("region_pk",)


# ViewSet по работе с Городами
class CityViewSet(
    generics.ListAPIView,
    generics.RetrieveAPIView,
    viewsets.GenericViewSet,
):
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [AllowAny]
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    search_fields = ("name",)
    filterset_class = CityFilter

    # Определяет координаты города (широту и долготу) и изменяет экземпляр данного города в БД
    def retrieve(self, request, *args, **kwargs):
        from services.yandex_geo import YandexGeocoderClient
        from config.settings import YANDEX_GEOCODER_API_KEY

        geocoder_client = YandexGeocoderClient(YANDEX_GEOCODER_API_KEY)
        city = self.get_object()
        if not (city.latitude and city.longitude):
            address_data = geocoder_client.get_coordinates_from_city(city)
            city.latitude, city.longitude = (
                address_data.latitude,
                address_data.longitude,
            )
            city.save()

        return super().retrieve(request, *args, **kwargs)


class CompanyProposalViewSet(
    viewsets.ModelViewSet
):
    queryset = Proposal.objects.all()
    serializer_class = ProposalSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        if "application_id" in request.data:
            application_id = request.data['application_id']
            instance.applications.remove(int(application_id))
        if "company_id" in request.data:
            company_id = request.data["company_id"]
            instance.companies.remove(int(company_id))

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        current_proposal = Proposal.objects.get(sender_company=request.data["sender_company"],
                                                special_id=request.data["special_id"])
        # Добавляю в таблицу proposals_companies новый экземпляр
        for i in request.data["companies"]:
            current_proposal.companies.add(int(i))
        # Добавляю в таблицу proposals_applications новый экземпляр
        for i in request.data["applications"]:
            current_proposal.applications.add(int(i))

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(methods=["GET"], detail=True)
    def companies(self, request, *args, **kwargs):
        proposal = Proposal.objects.get(special_id=kwargs['pk'])
        serializer = ProposalSerializer(proposal)
        # serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    # Метод для создания списков id компаний для рассылок предложений
    @staticmethod
    def make_new_list(lst):
        new_lst = []
        for i in lst:
            comp = i.company_id
            new_lst.append(comp)
        return new_lst

    # Все нижеуказанные функции необходимы для пересылки предложений от компании другим компаниям
    @action(["POST"], detail=False)
    def send_company_proposals_by_email(self, request):

        proposals = request.data.get('proposals')
        if len(proposals) > 0:
            for id in proposals:
                proposal_id = id
                if proposal_id:
                    proposal = Proposal.objects.get(id=proposal_id)
                    proposals_list = proposal.companies.through.objects.filter(proposal_id=proposal_id)
                    companies_ids_list = self.make_new_list(proposals_list)
                    link = f"http://localhost:3000/profile/proposal-page-companies/{proposal.special_id}"
                    for company_id in companies_ids_list:
                        current_company = Company.objects.get(id=company_id)
                        send_mail(
                            'Предложение от Вторпрайс',
                            f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.',
                            'vtorprice.mail@yandex.ru',
                            [current_company.email]
                        )
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(["POST"], detail=False)
    def send_company_proposals_by_whatsapp(self, request):
        whatsapp_url = 'https://whatsgate.ru/api/v1/send'
        whatsapp_api_key = 'ErLuLaoIRgODGlkATy3CNzLqpou8gRIn'
        whatsapp_id = '67506a033c2f8'
        proposals = request.data.get('proposals')
        if len(proposals) > 0:
            for id in proposals:
                proposal_id = id
                if proposal_id:
                    proposal = Proposal.objects.get(id=proposal_id)
                    proposals_list = proposal.companies.through.objects.filter(proposal_id=proposal_id)
                    companies_ids_list = self.make_new_list(proposals_list)
                    link = f"http://localhost:3000/profile/proposal-page-companies/{proposal.special_id}"
                    for company_id in companies_ids_list:
                        current_company = Company.objects.get(id=company_id)
                        data = {
                            "WhatsappID": whatsapp_id,  # "67506a033c2f8",
                            "async": False,
                            "recipient": {
                                "number": str(current_company.phone)  # "79021817834"
                            },
                            "message": {
                                "body": f'Предложение от Вторпрайс для компании {current_company.name} ' +
                                        f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.'

                            }
                        }
                        headers = {
                            'X-API-Key': whatsapp_api_key,
                            'Content-Type': 'application/json'
                        }
                        post(whatsapp_url, json.dumps(data), headers=headers)
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(["POST"], detail=False)
    def send_company_proposals_by_telegram(self, request):
        telegram_url = 'https://wappi.pro/tapi/sync/message/send'
        telegram_token = '829057d4cfa5725744320ef68101d722af0adb0e'
        profile_id = 'd5d94664-d392'
        proposals = request.data.get('proposals')
        if len(proposals) > 0:
            for id in proposals:
                proposal_id = id
                if proposal_id:
                    proposal = Proposal.objects.get(id=proposal_id)
                    proposals_list = proposal.companies.through.objects.filter(proposal_id=proposal_id)
                    companies_ids_list = self.make_new_list(proposals_list)
                    link = f"http://localhost:3000/profile/proposal-page-companies/{proposal.special_id}"
                    for company_id in companies_ids_list:
                        current_company = Company.objects.get(id=company_id)
                        data = {
                            "body": f'Предложение от Вторпрайс' +
                                    f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.',
                            "recipient": str(current_company.phone)
                        }
                        params = {"profile_id": profile_id}
                        headers = {
                            "Authorization": telegram_token,
                            'Content-Type': 'application/json'
                        }
                        post(telegram_url, json.dumps(data), headers=headers, params=params)
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)


class CompanyEquipmentProposalViewSet(
    viewsets.ModelViewSet
):
    queryset = EquipmentProposal.objects.all()
    serializer_class = EquipmentProposalSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        if "application_id" in request.data:
            application_id = request.data['application_id']
            instance.applications.remove(int(application_id))
        if "company_id" in request.data:
            company_id = request.data["company_id"]
            instance.companies.remove(int(company_id))

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        current_proposal = EquipmentProposal.objects.get(sender_company=request.data["sender_company"],
                                                         special_id=request.data["special_id"])
        # Добавляю в таблицу proposals_companies новый экземпляр
        for i in request.data["companies"]:
            current_proposal.companies.add(int(i))
        # Добавляю в таблицу proposals_applications новый экземпляр
        for i in request.data["applications"]:
            current_proposal.applications.add(int(i))

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(methods=["GET"], detail=True)
    def companies(self, request, *args, **kwargs):
        proposal = EquipmentProposal.objects.get(special_id=kwargs['pk'])
        serializer = EquipmentProposalSerializer(proposal)
        # serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    # Метод для создания списков id компаний для рассылок предложений
    @staticmethod
    def make_new_list(lst):
        new_lst = []
        for i in lst:
            comp = i.company_id
            new_lst.append(comp)
        return new_lst

    # Все нижеуказанные функции необходимы для пересылки предложений от компании другим компаниям
    @action(["POST"], detail=False)
    def send_company_equipment_proposals_by_email(self, request):
        proposals = request.data.get('proposals')
        if len(proposals) > 0:
            for id in proposals:
                proposal_id = id
                if proposal_id:
                    proposal = EquipmentProposal.objects.get(id=proposal_id)
                    proposals_list = proposal.companies.through.objects.filter(equipmentproposal_id=proposal_id)
                    companies_ids_list = self.make_new_list(proposals_list)
                    link = f"http://localhost:3000/profile/equipment_proposal-page-companies/{proposal.special_id}"
                    for company_id in companies_ids_list:
                        current_company = Company.objects.get(id=company_id)
                        send_mail(
                            'Предложение от Вторпрайс',
                            f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.',
                            'vtorprice.mail@yandex.ru',
                            [current_company.email]
                        )
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(["POST"], detail=False)
    def send_company_equipment_proposals_by_whatsapp(self, request):
        whatsapp_url = 'https://whatsgate.ru/api/v1/send'
        whatsapp_api_key = 'ErLuLaoIRgODGlkATy3CNzLqpou8gRIn'
        whatsapp_id = '67506a033c2f8'
        proposals = request.data.get('proposals')
        if len(proposals) > 0:
            for id in proposals:
                proposal_id = id
                if proposal_id:
                    proposal = EquipmentProposal.objects.get(id=proposal_id)
                    proposals_list = proposal.companies.through.objects.filter(equipmentproposal_id=proposal_id)
                    companies_ids_list = self.make_new_list(proposals_list)
                    link = f"http://localhost:3000/profile/equipment_proposal-page-companies/{proposal.special_id}"
                    for company_id in companies_ids_list:
                        current_company = Company.objects.get(id=company_id)
                        data = {
                            "WhatsappID": whatsapp_id,  # "67506a033c2f8",
                            "async": False,
                            "recipient": {
                                "number": str(current_company.phone)  # "79021817834"
                            },
                            "message": {
                                "body": f'Предложение от Вторпрайс для компании {current_company.name} ' +
                                        f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.'

                            }
                        }
                        headers = {
                            'X-API-Key': whatsapp_api_key,
                            'Content-Type': 'application/json'
                        }
                        post(whatsapp_url, json.dumps(data), headers=headers)
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(["POST"], detail=False)
    def send_company_equipment_proposals_by_telegram(self, request):
        telegram_url = 'https://wappi.pro/tapi/sync/message/send'
        telegram_token = '829057d4cfa5725744320ef68101d722af0adb0e'
        profile_id = 'd5d94664-d392'
        proposals = request.data.get('proposals')
        if len(proposals) > 0:
            for id in proposals:
                proposal_id = id
                if proposal_id:
                    proposal = EquipmentProposal.objects.get(id=proposal_id)
                    proposals_list = proposal.companies.through.objects.filter(equipmentproposal_id=proposal_id)
                    companies_ids_list = self.make_new_list(proposals_list)
                    link = f"http://localhost:3000/profile/equipment_proposal-page-companies/{proposal.special_id}"
                    for company_id in companies_ids_list:
                        current_company = Company.objects.get(id=company_id)
                        data = {
                            "body": f'Предложение от Вторпрайс' +
                                    f'Здравствуйте, перейдите по ссылке {link} для получения актуальных предложений для вашей компании.',
                            "recipient": str(current_company.phone)
                        }
                        params = {"profile_id": profile_id}
                        headers = {
                            "Authorization": telegram_token,
                            'Content-Type': 'application/json'
                        }
                        post(telegram_url, json.dumps(data), headers=headers, params=params)
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)


class SubscribeViewSet(
    viewsets.ModelViewSet
):
    queryset = Subscribe.objects.all()

    serializer_class = SubscribeSerializer

    # def retrieve(self, request, *args, **kwargs):
    #    company_subscribe = SubscribesCompanies.objects.get(company_id=kwargs['pk'])
    #    serializer = SubscribeCompanySerializer(company_subscribe)
    #    return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        # Закомментил так как выдавало по десять экземпляров на страницу, а здесь страницы не нужны
        # queryset = self.filter_queryset(self.get_queryset())

        # page = self.paginate_queryset(queryset)
        # if page is not None:
        #    serializer = self.get_serializer(page, many=True)
        #    return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(self.queryset, many=True)
        return Response(serializer.data)

    # @action(methods=["POST"], detail=False)
    # def create_payment(self, request):
    #    c = request.data
    #    c['time_end'] = request.data['time_begin']
    #    subscribe = Subscribe.objects.get(level=request.data['level'], period=request.data['period'])
    #    c['subscribe_id'] = subscribe.id


#
#    # serializer = SubscribeCompanySerializer(data=c)
#    # if serializer.is_valid():
#    #    serializer_data = serializer.validated_data
#    #    s_data = serializer.data
#
#    # else:
#    #    return Response(400)
#    confirmation_url = create_payment(c)
#
#    return Response({'confirmation_url': confirmation_url}, 200)
#
# @action(methods=["POST"], detail=False)
# def payment_acceptance(self, request):
#    response = json.loads(request.data)
#
#    if payment_acceptance(response):
#        Response(200)
#
#    return Response(404)


class CompanySubscribeViewSet(
    viewsets.ModelViewSet
):
    queryset = SubscribesCompanies.objects.all()
    permission_classes = (IsOwner,)
    serializer_class = SubscribeCompanySerializer

    def retrieve(self, request, *args, **kwargs):
        if kwargs["pk"] != 'NaN':
            company_subscribe = SubscribesCompanies.objects.filter(~Q(is_deleted=1), company_id=kwargs['pk'])
            if (len(company_subscribe) > 0):
                serializer = self.get_serializer(company_subscribe[0])
                return Response(serializer.data)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):

        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        instance.is_deleted = request.data['is_deleted']
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    @action(methods=["POST"], detail=False)
    def create_payment(self, request):
        c = request.data
        c['time_end'] = request.data['time_begin']
        subscribe = Subscribe.objects.get(level=request.data['level'], period=request.data['period'])
        c['subscribe_id'] = subscribe.id
        confirmation_url = create_payment(c)

        return Response({'confirmation_url': confirmation_url}, 200)

    @action(methods=["POST"], detail=False)
    def payment_acceptance(self, request):
        response = json.loads(request.data)

        if payment_acceptance(response):
            Response(200)

        return Response(404)
