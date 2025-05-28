import uuid

from bulk_update_or_create import BulkUpdateOrCreateQuerySet
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Case, When, Q, OuterRef, Value, Avg, Sum
from phonenumber_field.modelfields import PhoneNumberField

from chat.models import Chat
from common.model_fields import get_field_from_choices, AmountField
from common.models import (
    BaseNameModel,
    AddressFieldsModelMixin,
    BaseModel,
    DeliveryFieldsModelMixin,
)
from common.utils import get_current_user_id
from exchange.models import DealStatus

User = get_user_model()

USED_FOR_DRIVER = 'Указывается при типе контрагента "Водитель" '
USED_FOR_TRANSPORT_AND_DISPATCHER = (
    'Указывается при типе контрагента "Экспедитор/диспетчер" или "Транспортная '
    'компания"'
)
USED_FOR_TRANSPORT_COMPANY = (
    'Указывается при типе контрагента "Транспортная компания" '
)


def contractor_storage(instance, filename):
    ext = filename.split(".")[-1]
    uuid_filename = "{}.{}".format(uuid.uuid4(), ext)
    #return "contractor_storage/{0}".format(uuid_filename)
    return f'contractor_storage/contractor_{instance.name}/{uuid_filename}'


class ContractorType(models.IntegerChoices):
    TRANSPORT = 1, "Транспортная компания"
    DISPATCHER = 2, "Экспедитор/диспетчер"
    DRIVER = 3, "Водитель"


class Contractor(AddressFieldsModelMixin, BaseNameModel):
    contractor_type = get_field_from_choices("Тип компании", ContractorType)

    transport_owns_count = models.PositiveIntegerField(
        "Количество собственных Т/С",
        null=True,
        blank=True,
        help_text=USED_FOR_TRANSPORT_COMPANY,
    )

    avatar_or_company_logo = models.ImageField(
        "Селфи для аватара/Логотип компании",
        upload_to=contractor_storage,
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="contractor",
        verbose_name="Кем создан",
        default=get_current_user_id,
        editable=False,
    )

    documents = GenericRelation("exchange.DocumentModel")

    class Meta:
        verbose_name = "Контрагент"
        verbose_name_plural = "Контрагенты"
        db_table = "contractor"


class TransportApplicationStatus(models.IntegerChoices):
    AGREEMENT = 1, "Назначение логиста"
    LOADING = 2, "Машина загружена"
    UNLOADING = 3, "Машина выгружена"
    FINAL_ACCEPTANCE = 4, "Окончательная приемка"
    COMPLETED = 5, "Выполнена"
    CANCELED = 6, "Отменена"


RECYCLABLE_DEAL_TO_TRANSPORT_APPLICATION_STATUS_MAPPING = {
    TransportApplicationStatus.LOADING: DealStatus.LOADING,
    TransportApplicationStatus.UNLOADING: DealStatus.UNLOADING,
}


class LoadingType(models.IntegerChoices):
    REAR = 1, "Зад"
    SIDE = 2, "Бок"
    UPSIDE = 3, "Верх"


class LogistTransportApplicationStatus(models.IntegerChoices):
    NEW = 1, "Новая"
    APPROVED = 2, "Принято"
    DECLINED = 3, "Отклонено"
    PENDING = 4, "В процессе"


class TransportApplicationQuerySet(
    BulkUpdateOrCreateQuerySet, models.QuerySet
):
    def annotate_logist_status(self, user, *args, **kwargs):
        return self.annotate(
            logist_status=Case(
                When(
                    condition=Q(
                        id__in=LogisticsOffer.objects.filter(
                            logist=user,
                            application=OuterRef("pk"),
                            status=LogisticOfferStatus.APPROVED,
                        ).values("application")
                    ),
                    then=Value(LogistTransportApplicationStatus.APPROVED),
                ),
                When(
                    condition=Q(
                        id__in=LogisticsOffer.objects.filter(
                            logist=user,
                            application=OuterRef("pk"),
                            status=LogisticOfferStatus.PENDING,
                        ).values("application")
                    ),
                    then=Value(LogistTransportApplicationStatus.PENDING),
                ),
                When(
                    condition=Q(
                        id__in=LogisticsOffer.objects.filter(
                            logist=user,
                            application=OuterRef("pk"),
                            status=LogisticOfferStatus.DECLINED,
                        ).values("application")
                    ),
                    then=Value(LogistTransportApplicationStatus.DECLINED),
                ),
                default=Value(LogistTransportApplicationStatus.NEW),
            )
        )

    def get_average_delivery_price(self):
        return (
            self.aggregate(
                average_price=Avg("approved_logistics_offer__amount")
            )["average_price"]
            or 0.0
        )

    def get_total_delivery_sum(self):
        return (
            self.aggregate(total_sum=Sum("approved_logistics_offer__amount"))[
                "total_sum"
            ]
            or 0.0
        )

    def get_total_weight(self):
        return (
            self.aggregate(total_weight=Sum("weight"))["total_weight"] or 0.0
        )

    def get_completed(self):
        return self.filter(status=TransportApplicationStatus.COMPLETED)


class TransportApplication(DeliveryFieldsModelMixin, BaseModel):
    sender = models.CharField("Отправитель", max_length=64)
    recipient = models.CharField("Получатель", max_length=64)
    status = get_field_from_choices(
        "Статус",
        TransportApplicationStatus,
        default=TransportApplicationStatus.AGREEMENT,
    )
    cargo_type = models.CharField("Характер груза", max_length=32)
    loading_type = get_field_from_choices("Формат погрузки", LoadingType)
    weight = models.FloatField("Вес (кг.)")

    shipping_city = models.ForeignKey(
        "company.City",
        verbose_name="Город отгрузки",
        on_delete=models.SET_NULL,
        related_name="shipping_transport_app",
        null=True,
        blank=True,
    )
    delivery_city = models.ForeignKey(
        "company.City",
        verbose_name="Город доставки",
        on_delete=models.SET_NULL,
        related_name="delivery_transport_app",
        null=True,
        blank=True,
    )

    sender_phone = PhoneNumberField("Номер телефона отправителя", null=True)
    receiver_phone = PhoneNumberField("Номер телефона получателя", null=True)

    loading_hours = models.CharField(
        "Часы погрузки", max_length=12, default="", blank=True
    )
    weekend_work = models.BooleanField("Работа в выходные", default=False)
    comment = models.TextField("Комментарий", default="", blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="transport_applications",
        verbose_name="Кем создан",
        default=get_current_user_id,
        editable=False,
    )

    shipping_date = models.DateTimeField(
        "Дата отгрузки", null=True, blank=True
    )
    delivery_date = models.DateField("Дата прибытия", null=True, blank=True)
    loaded_weight = models.FloatField(
        "Загруженный вес",
        null=True,
        blank=True,
        help_text="Поле для справки, не влияет на расчет стоимости",
    )

    accepted_weight = models.FloatField(
        "Принятый вес",
        null=True,
        blank=True,
        help_text="Поле для справки, не влияет на расчет стоимости",
    )

    approved_logistics_offer = models.OneToOneField(
        "LogisticsOffer",
        verbose_name="Выбранное предложение логиста",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    deal = GenericForeignKey("content_type", "object_id")
    documents = GenericRelation("exchange.DocumentModel")

    objects = TransportApplicationQuerySet.as_manager()

    class Meta:
        verbose_name = "Заявка на транспорт"
        verbose_name_plural = "Заявки на транспорт"
        db_table = "transport_applications"

        unique_together = [["object_id", "content_type"]]

    def get_approved_offer(self):
        return self.offers.get(status=LogisticOfferStatus.APPROVED)


class LogisticOfferStatus(models.IntegerChoices):
    PENDING = 1, "На рассмотрении"
    APPROVED = 2, "Одобрено"
    DECLINED = 3, "Отклонено"


class LogisticsOffer(BaseNameModel):
    status = get_field_from_choices(
        "Статус предложения",
        LogisticOfferStatus,
        default=LogisticOfferStatus.PENDING,
    )
    amount = AmountField("Стоимость доставки")
    shipping_date = models.DateTimeField("Дата загрузки")
    logist = models.ForeignKey(
        User, on_delete=models.CASCADE, default=get_current_user_id
    )
    application = models.ForeignKey(
        TransportApplication, on_delete=models.CASCADE, related_name="offers"
    )
    contractor = models.ForeignKey(
        Contractor, on_delete=models.CASCADE, verbose_name="Контрагент"
    )
    chat = models.OneToOneField(
        "chat.Chat", on_delete=models.CASCADE, verbose_name="Чат", null=True
    )

    class Meta:
        db_table = "logistic_offers"
        verbose_name = "Предложение логиста"
        verbose_name_plural = "Предложения логистов"

    def decline_all_other_offers(self):
        """
        Declines all other logistic offers on TransportApplication
        """
        all_other_offers = self.application.offers.all().exclude(pk=self.pk)

        all_other_offers.update(status=LogisticOfferStatus.DECLINED)

    def save(
        self,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        is_created = True if self.pk is None else False
        super().save(force_insert, force_update, using, update_fields)

        if is_created:
            self.chat = Chat.objects.create(
                name=f"Предложение по логистике № {self.pk} к заявке № {self.application.pk}"
            )
            self.save()
