from datetime import datetime, timedelta
from typing import Optional, Union

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count
from drf_yasg.utils import swagger_auto_schema
from pydantic import BaseModel
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg import openapi as api

from common.views import MultiSerializerMixin
from company.models import Company
from document_generator.api.serializers import GeneratedDocumentSerializer
from document_generator.common import get_or_generate_document
from document_generator.generators.document_generators import (
    InvoiceDocument,
    Act,
)
from document_generator.models import (
    GeneratedDocumentType,
    GeneratedDocumentModel,
)
from exchange.models import RecyclablesApplication, EquipmentApplication, RecyclablesDeal
from exchange.utils import get_truncation_class
from finance.api.models import ManagerPaymentsOutput, TotalForMonth
from finance.api.serializers import (
    InvoicePaymentSerializer,
    CreatePaymentOrderSerializer,
)
from finance.models import InvoicePayment, InvoicePaymentStatus, PaymentOrder
from statistic.api.models import GraphPoint, Graph
from user.models import UserRole


# Имитация моделей из бд для собра аггрегированных данных
class PseudoApplication(BaseModel):
    volume: int
    price: int
    images: Optional[str]


class PseudoDeal(BaseModel):
    weight: Optional[int]
    id: str = "Весь месяц"
    buyer_company: Optional[Company]
    application: Optional[
        Union[RecyclablesApplication, EquipmentApplication, PseudoApplication]
    ]
    price: Optional[int]
    deal_number: Optional[str]

    class Config:
        arbitrary_types_allowed = True


class PseudoInvoice(BaseModel):
    id: str = "весь месяц"
    deal: PseudoDeal


class InvoicePaymentViewSet(MultiSerializerMixin, viewsets.ModelViewSet):
    queryset = InvoicePayment.objects.all()
    permission_classes = [IsAuthenticated]
    default_serializer_class = InvoicePaymentSerializer
    parser_classes = [MultiPartParser, FormParser]

    serializer_classes = {
        "send_payment_order": CreatePaymentOrderSerializer,
        "all_month_order": CreatePaymentOrderSerializer,
        "get_payment_bill": GeneratedDocumentSerializer,
    }

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_anonymous:
            return qs.none()
        if user.role == UserRole.COMPANY_ADMIN:
            return qs.filter(company=user.company).for_this_month()
        if user.role == UserRole.MANAGER:
            return qs.filter(company__manager=user).paid()
        if user.role == UserRole.ADMIN:
            return qs

        return qs

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            api.Parameter(
                "id",
                api.IN_QUERY,
                description="Идентификатор платежа",
                type=api.TYPE_INTEGER,
                required=False,
            )
        ],
    )
    @action(detail=False, methods=["get"])
    def get_payment_bill(self, request, *args, **kwargs):
        """
        Получить счет на оплату
        """
        user = self.request.user
        if user.is_anonymous:
            raise NotAuthenticated

        pk = request.query_params.get("id")

        content_type = ContentType.objects.get_for_model(InvoicePayment)

        t = self.get_queryset()[0]
        deal_m = t.deals.get(id=t.object_id)
        application_m = deal_m.application
        if pk:
            invoice_payment = get_object_or_404(self.get_queryset(), pk=pk)
            generator = InvoiceDocument(invoice_payment)
            document_type = GeneratedDocumentType.INVOICE_DOCUMENT
            document = get_or_generate_document(
                generator=generator,
                document_filter_kwargs={
                    "content_type": content_type,
                    "object_id": invoice_payment.id,
                    "type": document_type,
                },
            )
        else:
            invoice_payment = self.get_queryset()
            # Агрегация происходит через модель RecyclablesDeal поле invoice (GenericForeignKey(RecyclablesApplication),
            # related_query_name="deals") и поле weight в RecyclablesDeal

            total_weight = invoice_payment.aggregate(
                total_weight=models.Sum("deals__weight")
            )["total_weight"]
            total_price = invoice_payment.aggregate(
                total_weight=models.Sum("deals__price")
            )["total_weight"]

            # application = PseudoApplication(
            #    volume=total_weight, price=total_price, images=''
            # )

            application_m.volume = total_weight
            application_m.price = total_price
            application_m.save()

            deal_m = RecyclablesDeal(
                id=deal_m.id,
                weight=total_weight,
                buyer_company=user.company,
                price=total_price,
                application=application_m,
                deal_number=deal_m.deal_number,
                supplier_company=deal_m.supplier_company
            )
            # deal = PseudoDeal(
            #    weight=total_weight,
            #    buyer_company=user.company,
            #    price=total_price,
            #    application=application,
            #    deal_number="За весь месяц",
            # )
            # invoice = PseudoInvoice(deal=deal)
            invoice_m = InvoicePayment(deal=deal_m)
            # Get total sum of all unpaid invoice payments
            generated_document = InvoiceDocument(
                # invoice
                invoice_m
            ).replace_all_and_save()
            to_create = []
            gen_doc = GeneratedDocumentModel.objects.filter(object_id=1, document=generated_document)
            for document in gen_doc:
                document.delete()

            for item in invoice_payment:
                content_type = ContentType.objects.get_for_model(item)
                to_create.append(
                    GeneratedDocumentModel(
                        document=generated_document,
                        type=GeneratedDocumentType.INVOICE_DOCUMENT,
                        content_object=item.deal,
                    )
                )
            created = GeneratedDocumentModel.objects.bulk_create(to_create)
            if created:
                return Response(GeneratedDocumentSerializer(created[-1]).data)
            return Response(None)

        return Response(GeneratedDocumentSerializer(document).data)

    @swagger_auto_schema(
        method="get",
    )
    @action(detail=True, methods=["get"])
    def get_act(self, request, pk=None, *args, **kwargs):
        invoice: InvoicePayment = self.get_object()
        user = request.user
        deal = invoice.deal

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

    @action(detail=True, methods=["post"])
    def send_payment_order(self, request, pk=None, *args, **kwargs):
        """
        Отправить платежное поручение
        """
        invoice_payment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invoice_payment.status = InvoicePaymentStatus.PAID
        invoice_payment.save()

        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def all_month_order(self, request, pk=None, *args, **kwargs):
        """
        Отправить платежное поручение
        """
        user = self.request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoices = (
            self.get_queryset()
            .filter(company=user.company, is_deleted=False)
            .for_this_month()
            .unpaid()
        )
        for invoice_payment in invoices:
            serializer.save(invoice_payment=invoice_payment)
        invoices.update(status=InvoicePaymentStatus.PAID)
        return Response(serializer.data)

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            api.Parameter(
                "from_date",
                api.IN_QUERY,
                description="Дата начала",
                type=api.TYPE_STRING,
                required=False,
            ),
            api.Parameter(
                "to_date",
                api.IN_QUERY,
                description="Дата конца",
                type=api.TYPE_STRING,
                required=False,
            ),
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить график(week/month/year/all)",
            ),
        ],
    )
    @action(detail=False, methods=["get"])
    def manager_payments(self, request):
        if request.user.role not in [UserRole.MANAGER, UserRole.ADMIN]:
            raise PermissionDenied

        queryset = self.get_queryset()
        from_date, to_date, period = self.__get_manager_payment_parameters(
            request.query_params
        )

        if from_date and to_date:
            queryset = queryset.filter(created_at__range=(from_date, to_date))

        paginator_class = self.pagination_class()
        paginated_queryset = paginator_class.paginate_queryset(
            queryset, request, view=self
        )

        to_update = list(map(lambda x: x.id, paginated_queryset))

        response = paginator_class.get_paginated_response(
            InvoicePaymentSerializer(paginated_queryset, many=True).data
        )
        InvoicePayment.objects.filter(id__in=to_update).update(is_read=True)

        return response

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            api.Parameter(
                "from_date",
                api.IN_QUERY,
                description="Дата начала",
                type=api.TYPE_STRING,
                required=False,
            ),
            api.Parameter(
                "to_date",
                api.IN_QUERY,
                description="Дата конца",
                type=api.TYPE_STRING,
                required=False,
            ),
            api.Parameter(
                "period",
                api.IN_QUERY,
                type=api.TYPE_STRING,
                required=False,
                description="Период по которому выводить график(week/month/year/all)",
            ),
        ],
    )
    @action(detail=False, methods=["get"])
    def manager_payments_graph_data(self, request):
        if request.user.role not in [UserRole.MANAGER, UserRole.ADMIN]:
            raise PermissionDenied

        queryset = self.get_queryset()
        from_date, to_date, period = self.__get_manager_payment_parameters(
            request.query_params
        )
        if from_date and to_date:
            queryset = queryset.filter(created_at__range=(from_date, to_date))
        TruncClass = get_truncation_class(period)
        total_sum_of_sells, total_vtorprice_earnings = self.__get_totals(
            queryset
        )

        graph_data = Graph(
            points=self._get_count_graph_data(
                TruncClass, queryset, "created_at"
            )
        )
        manager_data_output = ManagerPaymentsOutput(
            graph=graph_data,
            total_sum_of_sells=total_sum_of_sells,
            total_vtorprice_earnings=total_vtorprice_earnings,
        )
        return Response(manager_data_output.dict())

    @action(detail=False, methods=["get"])
    def total_per_month(self, request):
        total = (
                self.get_queryset().aggregate(total=models.Sum("amount"))["total"]
                or 0.0
        )

        return Response(TotalForMonth(total=total).dict())

    def __get_totals(self, queryset):
        total_sum_of_sells = sum(map(lambda x: x.deal.total_price, queryset))
        invoices_id = queryset.values_list("id", flat=True)
        orders = PaymentOrder.objects.filter(
            invoice_payment__id__in=invoices_id
        )

        total_vtorprice_earnings = orders.aggregate(
            earnings=models.Sum("total")
        )["earnings"]
        return total_sum_of_sells, total_vtorprice_earnings

    def __get_manager_payment_parameters(self, query_params):
        from_date_raw = query_params.get("from_date")
        to_date_raw = query_params.get("to_date")
        period = query_params.get("period", "week")

        if not from_date_raw:
            from_date, to_date = self.__get_date_from_peroid(period)
        elif from_date_raw and not to_date_raw:
            from_date, to_date = (
                datetime.fromisoformat(from_date_raw.replace("Z", "")),
                datetime.now(),
            )
        else:
            from_date, to_date = datetime.fromisoformat(
                from_date_raw.replace("Z", "")
            ), datetime.fromisoformat(to_date_raw.replace("Z", ""))

        return from_date, to_date, period

    def __get_date_from_peroid(self, period: str):
        if period == "week":
            return datetime.now() - timedelta(days=7), datetime.now()
        if period == "month":
            return datetime.now() - timedelta(days=30), datetime.now()
        if period == "year":
            return datetime.now() - timedelta(days=365), datetime.now()
        return None, None

    @staticmethod
    def _get_count_graph_data(
            TruncClass, qs, field_to_truncate="delivery_date"
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
