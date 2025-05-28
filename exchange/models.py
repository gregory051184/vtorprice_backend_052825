import uuid

from bulk_update_or_create import BulkUpdateOrCreateQuerySet
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from decimal import Decimal

from django.db.models import (
    Case,
    When,
    F,
    FloatField,
    Q,
)
from django.urls import reverse

from chat.models import Chat
from common.model_fields import (
    get_field_from_choices,
    AmountField,
    LatitudeField,
    LongitudeField,
)
from common.models import (
    BaseModel,
    DeliveryFieldsModelMixin,
    AddressFieldsModelMixin, BaseNameDescModel, BaseNameModel,
)
from common.utils import (
    subtract_percentage,
    get_nds_amount,
    get_current_user_id,
    generate_random_sequence,
)
from company.models import CompanyStatus, Company
from exchange.signals import deal_completed, application_status_changed

User = get_user_model()


class DocumentType(models.IntegerChoices):
    UNLOADING_AGREMEENT = 1, "Договор на отгрузку"
    AGREEMENT_APPLICATION = 2, "Договор-заявка"
    WAYBILL = 3, "Товарно-транспортная накладная"
    INVOICE = 4, "Счет-фактура"
    AGREEMENT_SPECIFICATION = 5, "Договор приложение спецификация"
    UNIFORM_TRANSPORTATION_DOCUMENT = (
        6,
        "Унифицированный транспортный документ",
    )
    ACT = 7, "Акт"
    INVOICE_DOCUMENT = 8, "Платежный счет"


def exchange_storage(instance, filename):
    ext = filename.split(".")[-1]
    uuid_filename = "{}.{}".format(uuid.uuid4(), ext)
    # return "exchange_storage/{0}".format(uuid_filename)
    return f'exchange_storage/{instance.content_object}_id_{instance.object_id}/{uuid_filename}'


class DocumentModel(BaseModel):
    name = models.CharField(blank=True, max_length=512)
    document = models.FileField("Документ", upload_to=exchange_storage)
    content_type = models.ForeignKey(
        ContentType, verbose_name="Тип контента", on_delete=models.CASCADE
    )
    company = models.ForeignKey(
        Company, verbose_name="Компания", on_delete=models.CASCADE, null=True
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    document_type = get_field_from_choices(
        "Тип документа", DocumentType, null=True
    )

    class Meta:
        verbose_name = "Документ сделки"
        verbose_name_plural = "Документы сделки"

        indexes = [models.Index(fields=["content_type", "object_id"])]
        db_table = "documents"

    def __str__(self):
        return self.document.url


class ImageModel(models.Model):
    image = models.ImageField("Изображение", upload_to=exchange_storage)
    content_type = models.ForeignKey(
        ContentType, verbose_name="Тип контента", on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]
        db_table = "images"

    def __str__(self):
        return self.image.url


class DealType(models.IntegerChoices):
    BUY = 1, "Покупка"
    SELL = 2, "Продажа"


class UrgencyType(models.IntegerChoices):
    READY_FOR_SHIPMENT = 1, "Готово к отгрузке"
    SUPPLY_CONTRACT = 2, "Контракт на поставку"


class PackingAccountingType(models.IntegerChoices):
    INCLUDED = 1, "Входит в стоимость"
    SUBTRACTED = 2, "Вычитается"


class PackingDeductionType(models.IntegerChoices):
    FROM_BALE = 1, "На упаковку с каждой кипы"
    FROM_TOTAL_WEIGHT = 2, "На упаковку с общего веса"


class ApplicationSaveMixin(models.Model):
    def save(
            self,
            force_insert=False,
            force_update=False,
            using=None,
            update_fields=None,
    ):
        created = False
        if self.pk is None:
            created = True

        if created:
            if self.company.status in (
                    CompanyStatus.VERIFIED,
                    CompanyStatus.RELIABLE,
            ):
                self.status = ApplicationStatus.PUBLISHED
            else:
                self.status = ApplicationStatus.ON_REVIEW

        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        abstract = True


class ApplicationStatus(models.IntegerChoices):
    ON_REVIEW = 1, "На проверке"
    PUBLISHED = 2, "Опубликована"
    CLOSED = 3, "Завершена"
    DECLINED = 4, "Отклонена"


class ApplicationRecyclableStatus(models.IntegerChoices):
    WASTE = 1, "Отходы"
    GRANULE = 2, "Гранула"


class SpecialApplicationPeriod(models.IntegerChoices):
    DAY = 1, "День"
    TWO_DAYS = 2, "2 Дня"
    FOUR_DAYS = 3, "4 Дня"
    WEEK = 4, "7 Дней"


class RecyclablesApplicationQuerySet(
    BulkUpdateOrCreateQuerySet, models.QuerySet
):
    def annotate_total_weight(self, *args, **kwargs):
        return self.annotate(
            total_weight=Case(
                When(
                    Q(full_weigth__gt=0) & Q(full_weigth__isnull=False),
                    then=F("full_weigth"),
                ),
                When(
                    urgency_type=UrgencyType.READY_FOR_SHIPMENT,
                    then=F("bale_count") * F("bale_weight"),
                ),
                When(
                    urgency_type=UrgencyType.SUPPLY_CONTRACT, then=F("volume")
                ),
                output_field=FloatField(),
            )
        )

    # TODO: make this stuff working
    #
    # def annotate_price(self):
    #     return self.annotate(
    #         actual_price=ExpressionWrapper(
    #             Case(
    #                 When(
    #                     urgency_type=UrgencyType.SUPPLY_CONTRACT,
    #                     then=Coalesce(F("volume"), 0) * F("price")
    #                 ),
    #                 When(
    #                     urgency_type=UrgencyType.READY_FOR_SHIPMENT,
    #                     then=Coalesce(F("bale_count"), 0) * Coalesce(F("bale_weight"), 0) * F("price"),
    #                 )
    #             ),
    #             output_field=IntegerField(),
    #         ),
    #     )
    #
    # def aggregate_total_price(self):
    #     return self.annotate_price().aggregate(Sum("actual_price"))


class BaseRecyclablesApplication(BaseModel):
    with_nds = models.BooleanField("С НДС", default=False)
    price = AmountField("Цена за единицу веса")
    weediness = models.FloatField("Сорность в %", null=True, blank=True)
    moisture = models.FloatField(
        "Влага или посторонние включения в %", null=True, blank=True
    )
    is_packing_deduction = models.BooleanField(
        "Упаковка вычитается",
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    packing_deduction_type = get_field_from_choices(
        "Вычет",
        PackingDeductionType,
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    packing_deduction_value = models.PositiveSmallIntegerField(
        "Значение вычета",
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    comment = models.TextField("Комментарий", default="", blank=True)

    class Meta:
        abstract = True


class RecyclablesApplication(BaseRecyclablesApplication, ApplicationSaveMixin):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="recyclables_applications",
    )
    recyclables = models.ForeignKey(
        "product.Recyclables",
        verbose_name="Вторсырье",
        on_delete=models.CASCADE,
        related_name="applications",
    )

    application_recyclable_status = get_field_from_choices(
        "Статус Фракции",
        ApplicationRecyclableStatus,
        default=ApplicationRecyclableStatus.WASTE,
    )

    status = get_field_from_choices(
        "Статус",
        ApplicationStatus,
        default=ApplicationStatus.ON_REVIEW,
    )
    deal_type = get_field_from_choices("Тип сделки", DealType)
    urgency_type = get_field_from_choices("Срочность", UrgencyType)
    bale_count = models.FloatField(
        "Количество кип",
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    bale_weight = models.FloatField(
        "Вес одной кипы",
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    volume = models.FloatField(
        "Объем",
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки контракт на поставку",
    )
    lot_size = models.FloatField(
        "Лотность",
        null=True,
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    images = GenericRelation(
        "exchange.ImageModel",
        verbose_name="Фотографии вторсырья",
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )
    video_url = models.CharField(
        "Ссылка на видео",
        max_length=512,
        default="",
        blank=True,
        help_text="Указывается, если тип заявки готово к отгрузке",
    )

    full_weigth = models.PositiveIntegerField("Полный вес заявки", null=True)

    # Address
    city = models.ForeignKey(
        "company.City",
        verbose_name="Город",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    address = models.CharField(
        "Адрес", max_length=1024, default="", blank=True
    )
    latitude = LatitudeField(blank=True, null=True)
    longitude = LongitudeField(blank=True, null=True)

    objects = RecyclablesApplicationQuerySet.as_manager()

    class Meta:
        verbose_name = "Заявка по вторсырью"
        verbose_name_plural = "Заявки по вторсырью"
        db_table = "recyclables_applications"

    @staticmethod
    def get_total_weight(application):
        if application.full_weigth:
            return application.full_weigth
        if application.urgency_type == UrgencyType.READY_FOR_SHIPMENT:
            return application.bale_count * application.bale_weight
        return application.volume

    @staticmethod
    def get_price_including_deduction(
            weight: float,
            price: Decimal,
            bale_count: float,
            packing_deduction_type: PackingDeductionType.choices,
            packing_deduction_value: int,
    ):
        """
        Calculates the price, taking into account the deduction for packaging

        :param weight:
        :param price:
        :param bale_count:
        :param packing_deduction_type:
        :param packing_deduction_value:
        :return: Decimal
        """
        if packing_deduction_type == PackingDeductionType.FROM_TOTAL_WEIGHT:
            weight = subtract_percentage(weight, packing_deduction_value)
        elif packing_deduction_type == PackingDeductionType.FROM_BALE:
            weight = weight - bale_count * packing_deduction_value
        else:
            raise NotImplementedError
        return Decimal(weight) * price

    @property
    def total_price(self):
        total_weight = getattr(self, "total_weight", 0)
        if not total_weight:
            total_weight = self.get_total_weight(self)

        if self.urgency_type == UrgencyType.READY_FOR_SHIPMENT:
            # if self.is_packing_deduction:
            #     return self.get_price_including_deduction(
            #         total_weight,
            #         self.price,
            #         self.bale_count,
            #         self.packing_deduction_type,
            #         self.packing_deduction_value,
            #     )
            # else:
            return Decimal(total_weight) * self.price
        elif self.urgency_type == UrgencyType.SUPPLY_CONTRACT:
            return Decimal(self.volume) * self.price

    @property
    def nds_amount(self):
        if self.with_nds:
            return get_nds_amount(self.total_price)
        return Decimal("0")

    def save(
            self,
            force_insert=False,
            force_update=False,
            using=None,
            update_fields=None,
    ):
        old_status = self.status
        super().save(force_insert, force_update, using, update_fields)
        new_status = self.status
        if old_status != new_status:
            # Sending signal for notification
            application_status_changed.send_robust(
                self.__class__, instance=self, new_status=new_status
            )


class WhoDelivers(models.IntegerChoices):
    SUPPLIER = 1, "Поставщик"
    BUYER = 2, "Покупатель"
    VTORPRICE = 3, "ВторПрайс"


class DealStatus(models.IntegerChoices):
    AGREEMENT = 1, "Согласование условий"
    DISPATCHER_APPOINTMENT = 2, "Назначение логиста"
    LOADING = 3, "Машина загружена"
    UNLOADING = 4, "Машина выгружена"
    ACCEPTANCE = 5, "Окончательная приемка"
    COMPLETED = 6, "Сделка закрыта"
    PROBLEM = 7, "Проблемная сделка"
    CANCELED = 8, "Сделка отменена"


class PaymentTerm(models.IntegerChoices):
    UPON_LOADING = 1, "По факту погрузки"
    UPON_UNLOADING = 2, "По факту выгрузки"
    OTHER = 3, "Другое"


class RecyclablesDeal(DeliveryFieldsModelMixin, BaseRecyclablesApplication):
    status = get_field_from_choices(
        "Статус",
        DealStatus,
        default=DealStatus.AGREEMENT,
    )
    supplier_company = models.ForeignKey(
        "company.Company",
        verbose_name="Поставщик",
        on_delete=models.CASCADE,
        related_name="recyclables_sell_deals",
    )
    buyer_company = models.ForeignKey(
        "company.Company",
        verbose_name="Покупатель",
        on_delete=models.CASCADE,
        related_name="recyclables_buy_deals",
    )
    application = models.ForeignKey(
        "exchange.RecyclablesApplication",
        verbose_name="Заявка",
        on_delete=models.PROTECT,
        related_name="deals",
    )
    weight = models.FloatField(
        "Вес партии в кг",
        null=True,
        blank=True,
    )

    # Terms of payment
    payment_term = get_field_from_choices(
        "Условие оплаты",
        PaymentTerm,
        default=PaymentTerm.UPON_LOADING,
    )
    other_payment_term = models.CharField(
        "Иное условие оплаты", max_length=128, default="", blank=True
    )

    # Delivery
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
    shipping_date = models.DateTimeField(
        "Дата отгрузки", null=True, blank=True
    )
    delivery_date = models.DateField("Дата прибытия", null=True, blank=True)
    who_delivers = get_field_from_choices(
        "Кто доставляет", WhoDelivers, default=WhoDelivers.VTORPRICE
    )
    loading_hours = models.CharField(
        "Часы погрузки", max_length=12, default="", blank=True
    )
    buyer_pays_shipping = models.BooleanField(
        "Доставку оплачивает покупатель", default=True
    )
    shipping_city = models.ForeignKey(
        "company.City",
        verbose_name="Город отгрузки",
        on_delete=models.SET_NULL,
        related_name="shipping_recyclables_deal",
        null=True,
        blank=True,
    )
    delivery_city = models.ForeignKey(
        "company.City",
        verbose_name="Город доставки",
        on_delete=models.SET_NULL,
        related_name="delivery_recyclables_deal",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        editable=False,
        verbose_name="Пользователь создавший сделку",
        related_name="recyclables_deals",
        default=get_current_user_id,
    )

    chat = models.OneToOneField(
        Chat,
        on_delete=models.CASCADE,
        verbose_name="Чат сделки",
        related_name="deal",
    )

    deal_number = models.CharField(
        verbose_name="Номер сделки",
        default=generate_random_sequence,
        max_length=10,
    )

    reviews = GenericRelation("Review")

    documents = GenericRelation("DocumentModel")
    transport_applications = GenericRelation(
        "logistics.TransportApplication",
        related_query_name="deals",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    invoices = GenericRelation(
        "finance.InvoicePayment",
        related_query_name="deals",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        verbose_name = "Сделка по вторсырью"
        verbose_name_plural = "Сделка по вторсырью"
        db_table = "recyclables_deals"

    @property
    def total_price(self):
        if self.application.urgency_type == UrgencyType.READY_FOR_SHIPMENT:
            if self.is_packing_deduction:
                bale_count = self.weight // self.application.bale_weight
                return RecyclablesApplication.get_price_including_deduction(
                    self.weight,
                    self.price,
                    bale_count,
                    self.packing_deduction_type,
                    self.packing_deduction_value,
                )

        return Decimal(self.weight) * self.price if self.weight else None

    def __str__(self):
        return f"Сделка по вторсырью №{self.deal_number}"

    def get_absolute_url(self):
        return reverse("recyclables_deals-detail", kwargs={"pk": self.pk})

    def save(
            self,
            force_insert=False,
            force_update=False,
            using=None,
            update_fields=None,
    ):
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )
        if self.status == DealStatus.COMPLETED:
            deal_completed.send_robust(sender=self.__class__, instance=self)


class Review(BaseModel):
    rate = models.PositiveSmallIntegerField(
        verbose_name="Оценка",
        validators=[MaxValueValidator(5), MinValueValidator(1)],
    )
    comment = models.TextField(verbose_name="Комментарий")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, verbose_name="Кого оцениваем"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, default=get_current_user_id
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    class Meta:
        db_table = "reviews"
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"


class EquipmentApplication(
    BaseModel, AddressFieldsModelMixin, ApplicationSaveMixin
):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="equipment_applications",
    )

    # ДОБАВИЛ
    category = models.ForeignKey(
        "product.EquipmentCategory",
        verbose_name="Категория оборудование",
        on_delete=models.CASCADE,
        # related_name="equipment_category_applications",
        related_query_name="category_applications",
        blank=True,
        null=True
    )
    # ________________________________________________________________
    equipment = models.ForeignKey(
        "product.Equipment",
        verbose_name="Оборудование",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="equipment_applications"
    )
    status = get_field_from_choices(
        "Статус",
        ApplicationStatus,
        default=ApplicationStatus.ON_REVIEW,
    )
    deal_type = get_field_from_choices("Тип сделки", DealType)
    with_nds = models.BooleanField("С НДС", default=False)
    price = AmountField("Цена")
    count = models.PositiveIntegerField("Количество")
    manufacture_date = models.DateField("Дата производства")
    was_in_use = models.BooleanField("Б/У", default=False)
    sale_by_parts = models.BooleanField("Продажа по частям", default=False)
    images = GenericRelation(
        "exchange.ImageModel",
        verbose_name="Фотографии оборудования",
        blank=True,
    )
    video_url = models.CharField(
        "Ссылка на видео",
        max_length=512,
        default="",
        blank=True,
    )
    comment = models.TextField("Комментарий", default="", blank=True)

    class Meta:
        verbose_name = "Заявка по оборудованию"
        verbose_name_plural = "Заявки по оборудованию"
        db_table = "equipment_applications"

    @property
    def nds_amount(self):
        if self.with_nds:
            return get_nds_amount(self.price)
        return Decimal("0")

    def save(
            self,
            force_insert=False,
            force_update=False,
            using=None,
            update_fields=None,
    ):
        old_status = self.status
        super().save(force_insert, force_update, using, update_fields)
        new_status = self.status
        if old_status != new_status:
            # Sending signal for notification
            application_status_changed.send_robust(
                self.__class__, instance=self, new_status=new_status
            )

    def __str__(self):
        return self.equipment.name


class EquipmentDeal(BaseModel, DeliveryFieldsModelMixin):
    status = get_field_from_choices(
        "Статус",
        DealStatus,
        default=DealStatus.AGREEMENT,
    )
    supplier_company = models.ForeignKey(
        "company.Company",
        verbose_name="Поставщик",
        on_delete=models.CASCADE,
        related_name="equipment_sell_deals",
    )
    buyer_company = models.ForeignKey(
        "company.Company",
        verbose_name="Покупатель",
        on_delete=models.CASCADE,
        related_name="equipment_buy_deals",
    )
    application = models.ForeignKey(
        "exchange.EquipmentApplication",
        verbose_name="Заявка",
        on_delete=models.PROTECT,
        related_name="deals",
    )
    with_nds = models.BooleanField("С НДС", default=False)
    price = AmountField("Цена за единицу")
    count = models.PositiveIntegerField("Количество")

    # Terms of payment
    payment_term = get_field_from_choices(
        "Условие оплаты",
        PaymentTerm,
        default=PaymentTerm.UPON_LOADING,
    )
    other_payment_term = models.CharField(
        "Иное условие оплаты", max_length=128, default="", blank=True
    )

    weight = models.FloatField(
        "Вес в кг",
        null=True,
        blank=True,
    )

    # Delivery
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
    shipping_date = models.DateTimeField(
        "Дата отгрузки", null=True, blank=True
    )
    delivery_date = models.DateField("Дата прибытия", null=True, blank=True)
    who_delivers = get_field_from_choices(
        "Кто доставляет", WhoDelivers, default=WhoDelivers.VTORPRICE
    )
    buyer_pays_shipping = models.BooleanField(
        "Доставку оплачивает покупатель", default=True
    )
    shipping_city = models.ForeignKey(
        "company.City",
        verbose_name="Город отгрузки",
        on_delete=models.SET_NULL,
        related_name="shipping_equipment_deal",
        null=True,
        blank=True,
    )
    delivery_city = models.ForeignKey(
        "company.City",
        verbose_name="Город доставки",
        on_delete=models.SET_NULL,
        related_name="delivery_equipment_deal",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        editable=False,
        verbose_name="Пользователь создавший сделку",
        related_name="equipment_deals",
        default=get_current_user_id,
    )

    chat = models.OneToOneField(
        Chat,
        on_delete=models.CASCADE,
        verbose_name="Чат сделки",
        related_name="equipment_deal",
    )

    deal_number = models.CharField(
        verbose_name="Номер сделки",
        default=generate_random_sequence,
        max_length=10,
    )

    loading_hours = models.CharField(
        "Часы погрузки", max_length=12, default="", blank=True
    )

    comment = models.TextField("Комментарий", default="", blank=True)

    reviews = GenericRelation("Review")

    documents = GenericRelation("DocumentModel")

    class Meta:
        verbose_name = "Сделка по оборудованию"
        verbose_name_plural = "Сделки по оборудованию"
        db_table = "equipment_deals"

    @property
    def total_price(self):
        return self.price * self.count

    @property
    def nds_amount(self):
        if self.with_nds:
            return get_nds_amount(self.price)
        return Decimal("0")

    def __str__(self):
        return f"Сделка по оборудованию №{self.deal_number}"

    def save(
            self,
            force_insert=False,
            force_update=False,
            using=None,
            update_fields=None,
    ):
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )
        if self.status == DealStatus.COMPLETED:
            deal_completed.send_robust(sender=self.__class__, deal=self)


class SpecialApplicationPaidPeriod(BaseNameModel):
    price = models.FloatField(
        'Цена за период',
        null=True,
        blank=True,
    )


class BaseSpecialApplication(BaseModel):
    with_nds = models.BooleanField("С НДС", default=False)
    description = models.TextField("Описание", default="", blank=True)

    class Meta:
        abstract = True


class SpecialApplication(BaseSpecialApplication, AddressFieldsModelMixin, DeliveryFieldsModelMixin):
    companies = models.ManyToManyField(
        "company.Company",
        through='SpecialApps',
        verbose_name="Специальные заявки компаний",
        blank=True,
        related_name="companies_special_applications",
    )

    images = GenericRelation(
        "exchange.ImageModel",
        verbose_name="Фотографии для специальной заявки",
        blank=True,
        # help_text="Указывается, если тип заявки готово к отгрузке",
    )
    video_url = models.CharField(
        "Ссылка на видео",
        max_length=512,
        default="",
        blank=True,
        # help_text="Указывается, если тип заявки готово к отгрузке",
    )

    # period = get_field_from_choices(
    #    'Период специальной заявки',
    #    SpecialApplicationPeriod,
    #    default=SpecialApplicationPeriod.DAY
    # )
    period = models.ForeignKey(
        SpecialApplicationPaidPeriod,
        on_delete=models.CASCADE,
        related_name='periods',
        verbose_name='Период',
        null=True,
        blank=True
    )

    price = models.FloatField(
        'Цена специальной заявки',
        null=True,
        blank=True,
    )

    chat = models.OneToOneField(
        Chat,
        on_delete=models.CASCADE,
        verbose_name="Чат специльного предложения",
        related_name="special_app",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Специальная заявка"
        verbose_name_plural = "Специальные заявки"
        db_table = "special_applications"


class SpecialApps(BaseModel):
    special_application = models.ForeignKey(SpecialApplication, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    time_end = models.DateTimeField(verbose_name="Дата окончания специальной заявки")
    time_begin = models.DateTimeField(verbose_name="Дата начала специальной заявки")
    payment_number = models.CharField(verbose_name="Номер платежа", max_length=255, null=True, blank=True)
    payment_access = models.BooleanField(default=False, verbose_name="Успешность платежа", null=True, blank=True)
