import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from common.model_fields import AmountField, get_field_from_choices
from common.models import BaseModel, BaseNameModel


def payment_doc_storage(instance, filename):
    ext = filename.split(".")[-1]
    uuid_filename = "{}.{}".format(uuid.uuid4(), ext)
    #return "payment_documents_storage/{0}".format(uuid_filename)
    return f'payment_documents_storage/{instance.object_id}/{uuid_filename}'


class InvoicePaymentStatus(models.IntegerChoices):
    PENDING = 1, "Ожидает оплаты"
    PAID = 2, "Оплачен"
    CANCELED = 3, "Отменен"
    REFUNDED = 4, "Возврат"


class PaymentOrderTypes(models.IntegerChoices):
    SINGLE = 1, "За одну сделку"
    ALL_MONTH = 2, "За весь месяц"


class InvoicePaymentQuerySet(models.QuerySet):
    def paid(self):
        return self.filter(status=InvoicePaymentStatus.PAID)

    def unpaid(self):
        return self.exclude(status=InvoicePaymentStatus.PAID)

    def for_this_month(self):
        current_month_start_date = timezone.now().replace(
            day=1, hour=0, minute=0, second=0
        )
        return self.filter(created_at__gte=current_month_start_date)


class InvoicePayment(BaseModel):
    is_read = models.BooleanField("Прочитано", default=False)
    amount = AmountField("Сумма")
    status = get_field_from_choices(
        "Статус", InvoicePaymentStatus, default=InvoicePaymentStatus.PENDING
    )
    company = models.ForeignKey(
        "company.Company", verbose_name="Компания", on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    deal = GenericForeignKey("content_type", "object_id")

    objects = InvoicePaymentQuerySet.as_manager()

    class Meta:
        verbose_name = "Оплата счета"
        verbose_name_plural = "Оплаты счетов"
        db_table = "invoice_payments"


class PaymentOrder(BaseNameModel):
    type = get_field_from_choices(
        "Тип", PaymentOrderTypes, default=PaymentOrderTypes.SINGLE
    )
    document = models.FileField("Документ", upload_to=payment_doc_storage)
    invoice_payment = models.ForeignKey(
        InvoicePayment, on_delete=models.CASCADE
    )
    total = AmountField("Сумма")

    class Meta:
        verbose_name = "Платежное поручение"
        verbose_name_plural = "Платежные поручения"
        db_table = "payment_orders"
