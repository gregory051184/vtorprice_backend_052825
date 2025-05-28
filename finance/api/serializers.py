from datetime import datetime

from rest_framework import serializers

from common.serializers import NonNullDynamicFieldsModelSerializer
from common.utils import MONTH_MAPPING
from finance.models import (
    InvoicePayment,
    PaymentOrderTypes,
    PaymentOrder,
    InvoicePaymentStatus,
)


class InvoicePaymentSerializer(NonNullDynamicFieldsModelSerializer):
    payment_order = serializers.SerializerMethodField()

    class Meta:
        model = InvoicePayment

    def get_payment_order(self, instance: InvoicePayment):
        return PaymentOrderSerializer(
            instance.paymentorder_set, many=True
        ).data


class PaymentOrderSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = PaymentOrder


class CreatePaymentOrderSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = ("document", "total")

    def validate(self, attrs):
        view = self.context.get("view")
        user = self.context.get("request").user
        if view.action == "send_payment_order":
            self.validate_for_single_invoice(attrs, view, user)

        if view.action == "all_month_order":
            self.validate_for_multiple_invoices(attrs, user)

        return super().validate(attrs)

    def validate_for_multiple_invoices(self, attrs, user):
        invoices = (
            InvoicePayment.objects.filter(
                company=user.company, is_deleted=False
            )
            .for_this_month()
            .unpaid()
        )
        if not invoices:
            raise serializers.ValidationError(
                "Нет неоплаченных счетов за текущий месяц"
            )

    def validate_for_single_invoice(self, attrs, view, user):
        invoice_payment = view.get_object()
        if invoice_payment.status != InvoicePaymentStatus.PENDING:
            raise serializers.ValidationError(
                "Нельзя создать платежное поручение для оплаченного счета"
            )
        if invoice_payment.company != user.company:
            raise serializers.ValidationError(
                "Нельзя создать платежное поручение для счета другой компании"
            )

    def create(self, validated_data):
        view = self.context.get("view")
        user = self.context.get("request").user
        if view.action == "send_payment_order":
            validated_data["type"] = PaymentOrderTypes.SINGLE
            invoice = view.get_object()
            validated_data["invoice_payment"] = invoice
            name = f"Платежное поручение от {user.company.name} за счет №{invoice.pk}"

        if view.action == "all_month_order":
            validated_data["type"] = PaymentOrderTypes.ALL_MONTH
            current_month = MONTH_MAPPING.get(datetime.now().month)
            name = f"Платежное поручение от {user.company.name} за месяц {current_month}"

        validated_data["name"] = name
        return super().create(validated_data)

    def to_representation(self, instance):
        return PaymentOrderSerializer().to_representation(instance)
