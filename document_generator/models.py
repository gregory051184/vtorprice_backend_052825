# Create your models here.
import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from common.model_fields import get_field_from_choices
from common.models import BaseModel


def generated_document_storage(instance, filename):
    ext = filename.split(".")[-1]
    uuid_filename = "{}.{}".format(uuid.uuid4(), ext)
    # return "generated_storage/{0}".format(uuid_filename)
    return f'generated_storage/deal_id_{instance.object_id}/{uuid_filename}'


class GeneratedDocumentType(models.IntegerChoices):
    UNLOADING_AGREMEENT = 1, "Договор на отгрузку"
    AGREEMENT_APPLICATION = 2, "Договор-заявка"
    WAYBILL = 3, "Товарно-транспортная накладная"
    INVOICE = 4, "Счет-фактура"
    AGREEMENT_SPECIFICATION = 5, "Договор приложение спецификация"
    UNIFORM_TRANSPORTATION_DOCUMENT = (
        6,
        "Унифицированный транспортный документ",
    )
    ACT_BUYER = 7, "Акт Покупателя"
    ACT_SELLER = 8, "Акт Продавца"
    ACT_FULL_MONTH = 9, "Акт за полный месяц"
    INVOICE_DOCUMENT = 10, "Платежный счет"


class GeneratedDocumentModel(BaseModel):
    name = models.CharField(blank=True, max_length=512)
    document = models.FileField(
        "Документ", upload_to=generated_document_storage
    )
    type = get_field_from_choices("Тип документа", GeneratedDocumentType)
    content_type = models.ForeignKey(
        ContentType, verbose_name="Тип контента", on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "Сгенерированный документ"
        verbose_name_plural = "Сгенерированные документы"

        indexes = [models.Index(fields=["content_type", "object_id"])]
        db_table = "generated_documents"
