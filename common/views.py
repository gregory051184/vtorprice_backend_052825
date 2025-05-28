import os

from django.contrib.contenttypes.models import ContentType
from django.db.models import Exists, OuterRef
from django.http import QueryDict
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.generics import get_object_or_404

from django.db.models import Q

from common.serializers import EmptySerializer
from company.models import Company
from exchange.api.serializers import (
    CreateImageModelSerializer,
    CreateDocumentModelSerializer,
)
from exchange.models import ImageModel, DocumentModel, DealType, RecyclablesApplication, RecyclablesDeal, DealStatus, \
    UrgencyType, Review
from exchange.services import filter_qs_by_coordinates
from user.models import UserRole, Favorite
from drf_yasg import openapi as api


class BaseQuerySetMixin:
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class MultiSerializerMixin:
    """
    Overridden to support several serializers for actions
    """

    serializer_classes = dict()
    default_serializer_class = None

    def get_serializer_class(self):
        return self.serializer_classes.get(
            self.action, self.default_serializer_class
        )


class BulkCreateMixin:
    """
    Overridden to support bulk creation
    """

    create_with_removal = False

    # Меняет аргумент many на True при создании документации компании из списка документов
    def get_serializer(self, *args, **kwargs):
        if self.action == "create":
            if isinstance(kwargs.get("data", {}), list):
                kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "create":
            # To support bulk creation with preliminary
            # deletion of existing objects
            context["with_removal"] = self.create_with_removal
        return context


class CompanyOwnerQuerySetMixin:
    """
    Filter the queryset by owner's company
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.is_authenticated and user.role == UserRole.COMPANY_ADMIN:
            qs = qs.filter(company=user.my_company)

        return qs


# TODO: Нужно тестировать, применение не очевидно!
# Все переменные данного класса задаются внутри класса,
# в который наследуется от NestedRouteQuerySetMixin
class NestedRouteQuerySetMixin:
    """
    Implements filtering by nested route

    f.e.: /companies/{company_pk}/documents/{pk} --> filter the queryset by company_pk
    source: https://github.com/alanjds/drf-nested-routers
    """

    nested_route_lookup_field = None

    def get_queryset(self):
        qs = super().get_queryset()

        if self.nested_route_lookup_field in self.kwargs:
            lookup = self.nested_route_lookup_field.replace("pk", "id")
            qs = qs.filter(
                **{lookup: self.kwargs[self.nested_route_lookup_field]}
            )

        return qs


class ImagesMixin:
    """
    Implements methods for adding and removing images
    for models that are related with the ImageModel model
    via a GenericRelation
    """

    @staticmethod
    def create_instance_images(images, instance):
        content_type = ContentType.objects.get_for_model(instance._meta.model)
        to_create = []

        for image in images:
            to_create.append(
                ImageModel(
                    image=image,
                    content_type=content_type,
                    object_id=instance.id,
                )
            )
        # instance.images.clear()
        instance.images.bulk_create(to_create)

    @swagger_auto_schema(
        request_body=CreateImageModelSerializer,
    )
    @action(methods=["POST"], detail=True)
    def add_images(self, request, *args, **kwargs):
        instance = self.get_object()
        images = request.FILES.getlist("image")
        self.create_instance_images(images=images, instance=instance)
        return super().retrieve(request, *args, **kwargs)

    @action(
        methods=["DELETE"],
        detail=True,
        url_path="delete_image/(?P<image_pk>[^/.]+)",
    )
    def delete_image(self, request, image_pk=None, *args, **kwargs):
        image = get_object_or_404(ImageModel, id=int(image_pk))
        os.remove(os.getcwd() + '/media/' + str(image.image))
        instance = self.get_object()
        instance.images.filter(pk=image_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentsMixin:
    """
    Implements methods for adding and removing documents
    for models that are related with the DocumentModel
    via a GenericRelation
    """

    @staticmethod
    def create_instance_documents(
            documents, instance, name, company, document_type
    ):
        content_type = ContentType.objects.get_for_model(instance)
        to_create = []

        for document in documents:
            to_create.append(
                DocumentModel(
                    document=document,
                    content_type=content_type,
                    object_id=instance.pk,
                    name=name,
                    company=company,
                    document_type=document_type,
                )
            )

        DocumentModel.objects.bulk_create(to_create)

    @swagger_auto_schema(
        request_body=CreateDocumentModelSerializer,
    )
    @action(methods=["POST"], detail=True)
    def add_documents(self, request, *args, **kwargs):
        instance = self.get_object()
        company = request.user.company
        documents = request.FILES.getlist("document")
        name = request.POST.get("name")
        document_type = request.POST.get("document_type")
        self.create_instance_documents(
            documents=documents,
            instance=instance,
            name=name,
            company=company,
            document_type=document_type,
        )
        return super().retrieve(request, *args, **kwargs)

    @action(
        methods=["DELETE"],
        detail=True,
        url_path="delete_document/(?P<document_pk>[^/.]+)",
    )
    def delete_document(self, request, document_pk=None, *args, **kwargs):
        instance = self.get_object()
        os.remove(os.getcwd() + '/media/' + str(instance.document))
        instance.documents.filter(pk=document_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FavoritableMixin:
    """
    Implements logic of liking and disliking some objects.
    Adds additional API endpoint /objects/<id>/favorite that marks and unmarks given as favorite.
    Also, when requesting this objects, adds fields isFavorite representing whether this object marked as favorite or not
    """

    # Возвращает дополнительное поле is_favourite = True/False
    def get_queryset(self):
        queryset = super().get_queryset()
        requested_user: "user.models.User" = self.request.user

        if requested_user.is_anonymous:
            return queryset

        return queryset.annotate(
            is_favorite=Exists(
                Favorite.objects.filter(
                    user=requested_user,
                    content_type=ContentType.objects.get_for_model(
                        self.queryset.model
                    ),
                    object_id=OuterRef("id"),
                )
            )
        )

    @swagger_auto_schema(
        request_body=EmptySerializer,
    )
    @action(
        detail=True,
        methods=["PATCH"],
        description="Mark or unmarks given Recyclable as favorite",
        permission_classes=[IsAuthenticated],
    )
    def favorite(self, request, *args, **kwargs):
        obj = self.get_object()
        requested_user = request.user
        content_type = ContentType.objects.get_for_model(obj)
        favorite_object, created = Favorite.objects.get_or_create(
            user=requested_user,
            content_type=content_type,
            object_id=obj.id,
        )
        if not created:
            favorite_object.delete()
        return self.retrieve(request, *args, **kwargs)


class ExcludeMixin:
    """
    Implements the logic to exclude objects in the list
    method via the passed query parameter, which accepts
    a list of object ids to be excluded
    """

    def get_queryset(self):
        qs = super().get_queryset()

        exclude = self.request.query_params.getlist("exclude", [])

        if exclude:
            qs = qs.exclude(pk__in=exclude)

        return qs

    @swagger_auto_schema(
        manual_parameters=[
            api.Parameter(
                "exclude",
                api.IN_QUERY,
                type=api.TYPE_INTEGER,
                required=False,
                description="ID объекта(ов), который(ые) необходимо исключить",
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class RecyclableApplicationsQuerySetMixin:

    @staticmethod
    def get_urgency_type(qs, dick: QueryDict):
        recyclables = dick.get('recyclables')
        urgency_type = dick.get('urgency_type')

        if recyclables is not None and urgency_type is not None:
            return qs.filter(urgency_type=urgency_type, recyclables=recyclables) if dick.get(
                'ordering') is None else qs.filter(
                recyclables=recyclables[0],
                urgency_type=urgency_type[0]).order_by(dick.get('ordering'))

        if recyclables is None and urgency_type is not None:
            return qs.filter(urgency_type=urgency_type[0]) if dick.get('ordering') is None else qs.filter(
                urgency_type=urgency_type[0]).order_by(dick.get('ordering'))
        else:
            return qs if dick.get('ordering') is None else qs.order_by(dick.get('ordering'))

    def split_query_params(self, qs, dick: QueryDict, params):
        if dick.get('no_page'):
            return qs
        if dick.get('company'):
            company = dick.get('company')
            return self.get_urgency_type(qs, dick).filter(company_id=company)

        if params.get('pk') or dick.get('search') == '':
            return self.get_urgency_type(qs, dick)

        if dick.get('recyclable_id') and dick.get('company_id'):
            company_id = dick.get('company_id')
            recyclable_id = dick.get('recyclable_id')
            return self.get_urgency_type(qs, dick).filter(~Q(company_id=company_id[0])).filter(
                Q(recyclables_id=recyclable_id[0])).filter(
                ~Q(deal_type=DealType.SELL))

        if not dick.getlist("point", []) and self.get_urgency_type(qs, dick):
            return self.get_urgency_type(qs, dick)

        if dick.getlist("point", []):
            if dick.get('urgency_type'):
                qs = filter_qs_by_coordinates(qs, self.get_urgency_type(qs, dick))
                return qs
            else:
                qs = filter_qs_by_coordinates(qs, dick.getlist("point", []))
                return qs
        else:
            return qs


class CompanyQueryMixin:
    # Эти фильтры для страницы фильтрации компаний (/companies/main)
    def query_filters(self, query, request_params: QueryDict):
        qs = query

        if request_params.get('recyclables__recyclables'):
            recyclable = int(request_params.get('recyclables__recyclables'))
            companies = RecyclablesApplication.objects.filter(recyclables=recyclable).values_list(
                'company_id', flat=True)
            companies_ids = list(set(companies))
            qs = qs.filter(id__in=companies_ids)

        if request_params.get('company_failed_deals'):
            failed_deals = int(request_params.get('company_failed_deals'))
            if failed_deals == 2:
                buyer_companies_ids = RecyclablesDeal.objects.filter(status__lte=DealStatus.COMPLETED).values_list(
                    'buyer_company_id', flat=True)
                supplier_companies_ids = RecyclablesDeal.objects.filter(status__lte=DealStatus.COMPLETED).values_list(
                    'supplier_company_id', flat=True)
                companies_ids = list(set(list(buyer_companies_ids) + list(supplier_companies_ids)))
                qs = qs.filter(id__in=companies_ids)
            if failed_deals == 1:
                buyer_companies_ids = RecyclablesDeal.objects.filter(status__gte=DealStatus.PROBLEM).values_list(
                    'buyer_company_id', flat=True)
                supplier_companies_ids = RecyclablesDeal.objects.filter(status__gte=DealStatus.PROBLEM).values_list(
                    'supplier_company_id', flat=True)
                companies_ids = list(set(list(buyer_companies_ids) + list(supplier_companies_ids)))
                qs = qs.filter(id__in=companies_ids)

        if request_params.get('deals_count'):
            deals_count = int(request_params.get('deals_count'))
            buyer_companies_ids = RecyclablesDeal.objects.filter(status__lte=DealStatus.COMPLETED).values_list(
                'buyer_company_id', flat=True)
            supplier_companies_ids = RecyclablesDeal.objects.filter(status__lte=DealStatus.COMPLETED).values_list(
                'supplier_company_id', flat=True)
            companies_ids_by_deals = list(buyer_companies_ids) + list(supplier_companies_ids)
            current_companies_ids = []
            for company_id in companies_ids_by_deals:
                count = companies_ids_by_deals.count(company_id)
                if count >= deals_count:
                    current_companies_ids.append(company_id)
            qs = qs.filter(id__in=current_companies_ids)

        if request_params.get('company_volume'):
            clear_company_ids = []
            company_volume = int(request_params.get('company_volume'))
            applications = RecyclablesApplication.objects.filter(
                urgency_type=UrgencyType.SUPPLY_CONTRACT)
            for company_id in applications.values_list("company_id"):
                company_contracts_volume = []
                for app in applications:
                    if company_id == app.company_id:
                        company_contracts_volume.append(app.volume)
                if sum(company_contracts_volume) >= company_volume:
                    clear_company_ids.append(company_id)
            qs = qs.filter(id__in=clear_company_ids)

        if request_params.get('deal_type'):
            deal_type = int(request_params.get('deal_type'))
            if deal_type == 1:
                companies_ids = RecyclablesApplication.objects.filter(deal_type=DealType.BUY).values_list(
                    'company_id', flat=True)
                qs = qs.filter(id__in=companies_ids)
            if deal_type == 2:
                companies_ids = RecyclablesApplication.objects.filter(deal_type=DealType.SELL).values_list(
                    'company_id', flat=True)
                qs = qs.filter(id__in=companies_ids)

        if request_params.get('company_has_applications'):
            has_apps = request_params.get('company_has_applications')
            if has_apps == 1:
                companies = RecyclablesApplication.objects.filter(
                    urgency_type=UrgencyType.READY_FOR_SHIPMENT).values_list(
                    'company_id', flat=True)
                companies_ids = list(set(companies))
                qs = qs.filter(id__in=companies_ids)
            if has_apps == 2:
                companies = RecyclablesApplication.objects.filter(
                    urgency_type=UrgencyType.SUPPLY_CONTRACT).values_list(
                    'company_id', flat=True)
                companies_ids = list(set(companies))
                qs = qs.filter(id__in=companies_ids)

        if request_params.get('rate'):
            company_rate = int(request_params.get('rate'))
            clear_company_ids = []
            companies_ids = qs.values_list('id')
            company_reviews = Review.objects.all()
            if company_rate > 0:
                for company in companies_ids:
                    company_reviews_sum = []
                    for review in company_reviews:
                        if review.company_id == company:
                            company_reviews_sum.append(int(review.rate))
                    if sum(company_reviews_sum) > 0:
                        current_company_rate = round(sum(company_reviews_sum) / len(company_reviews_sum))
                        if current_company_rate >= company_rate:
                            clear_company_ids.append(company)
                qs = qs.filter(id__in=clear_company_ids)
            else:
                qs = qs
        return qs


class EquipmentApplicationsQuerySetMixin:

    @staticmethod
    def get_urgency_type(qs, dick: QueryDict):
        recyclables = dick.get('recyclables')
        urgency_type = dick.get('urgency_type')

        if recyclables is not None and urgency_type is not None:
            return qs.filter(urgency_type=urgency_type, recyclables=recyclables) if dick.get(
                'ordering') is None else qs.filter(
                recyclables=recyclables[0],
                urgency_type=urgency_type[0]).order_by(dick.get('ordering'))

        if recyclables is None and urgency_type is not None:
            return qs.filter(urgency_type=urgency_type[0]) if dick.get('ordering') is None else qs.filter(
                urgency_type=urgency_type[0]).order_by(dick.get('ordering'))
        else:
            return qs if dick.get('ordering') is None else qs.order_by(dick.get('ordering'))

    def split_query_params(self, qs, dick: QueryDict, params):
        if dick.get('company'):
            company = dick.get('company')
            return self.get_urgency_type(qs, dick).filter(company_id=company[0])

        if params.get('pk') or dick.get('search') == '':
            return self.get_urgency_type(qs, dick)

        if dick.get('recyclable_id') and dick.get('company_id'):
            company_id = dick.get('company_id')
            recyclable_id = dick.get('recyclable_id')
            return self.get_urgency_type(qs, dick).filter(~Q(company_id=company_id[0])).filter(
                Q(recyclables_id=recyclable_id[0])).filter(
                ~Q(deal_type=DealType.SELL))

        if not dick.getlist("point", []) and self.get_urgency_type(qs, dick):
            return self.get_urgency_type(qs, dick)

        if dick.getlist("point", []):
            if dick.get('urgency_type'):
                qs = filter_qs_by_coordinates(qs, self.get_urgency_type(qs, dick))
                return qs
            else:
                qs = filter_qs_by_coordinates(qs, dick.getlist("point", []))
                return qs
        else:
            return qs
