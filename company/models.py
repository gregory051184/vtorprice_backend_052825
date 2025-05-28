import uuid

from colorfield.fields import ColorField
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.urls import reverse
from model_utils import FieldTracker
from phonenumber_field.modelfields import PhoneNumberField

from common.model_fields import (
    get_field_from_choices,
    AmountField,
    LatitudeField,
    LongitudeField,
)
from common.models import (
    BaseModel,
    BaseNameDescModel,
    BaseNameModel,
    AddressFieldsModelMixin,
)
from common.utils import get_current_user_id
from company.signals import verification_status_changed
from user.models import UserRole, UserStatus

User = get_user_model()


def company_storage(instance, filename):
    ext = filename.split(".")[-1]
    uuid_filename = "{}.{}".format(uuid.uuid4(), ext)
    # return "company_storage/{0}".format(uuid_filename)
    if hasattr(instance, 'comment'):
        return f'company_storage/{instance.company.id}/{uuid_filename}'
    if hasattr(instance, 'name'):
        return f'company_storage/{instance.id}/{uuid_filename}'


class District(BaseNameModel):
    class Meta:
        verbose_name = "Округ"
        verbose_name_plural = "Округи"
        db_table = "districts"


class Region(BaseNameModel):
    district = models.ForeignKey(
        "company.District",
        verbose_name="Округ",
        on_delete=models.SET_NULL,
        related_name="regions_district",
        null=True)

    class Meta:
        verbose_name = "Регион"
        verbose_name_plural = "Регионы"
        db_table = "regions"


class City(BaseNameModel):
    region = models.ForeignKey(
        Region, verbose_name="Район", on_delete=models.SET_NULL, null=True
    )
    latitude = LatitudeField(null=True, blank=True)
    longitude = LongitudeField(null=True, blank=True)

    class Meta:
        verbose_name = "Город"
        verbose_name_plural = "Города"
        db_table = "cities"


class CompanyStatus(models.IntegerChoices):
    NOT_VERIFIED = 1, "Не проверенная"
    VERIFIED = 2, "Проверенная"
    RELIABLE = 3, "Надежная"
    NOT_RELIABLE = 4, "Ненадёжная"


class Company(AddressFieldsModelMixin, BaseNameDescModel):
    # Main
    image = models.ImageField(
        "Фото/логотип", upload_to=company_storage, null=True, blank=True
    )

    # bank information
    inn = models.CharField(
        "ИНН", unique=True, db_index=True, max_length=32, blank=True
    )
    bic = models.CharField(
        "БИК", unique=False, max_length=15, null=True, blank=True
    )
    payment_account = models.CharField(
        "Расчетный счет", max_length=32, null=True, blank=True
    )
    correction_account = models.CharField(
        "Корресп. счет", unique=False, max_length=32, null=True, blank=True
    )
    bank_name = models.CharField(
        "Наименование банка",
        unique=False,
        max_length=100,
        null=True,
        blank=True,
    )
    status = get_field_from_choices(
        "Статус", CompanyStatus, default=CompanyStatus.NOT_VERIFIED
    )
    head_full_name = models.CharField(
        "ФИО директора", max_length=100, null=True
    )

    owner = models.OneToOneField(
        User,
        verbose_name="Владелец",
        on_delete=models.PROTECT,
        related_name="my_company",
        limit_choices_to={"role": UserRole.COMPANY_ADMIN},
        null=True,
        blank=True,
    )
    staff = ArrayField(models.IntegerField(), blank=True, default=list)

    suspend_staff = ArrayField(models.IntegerField(), blank=True, default=list)

    manager = models.ForeignKey(
        User,
        verbose_name="Менеджер",
        on_delete=models.PROTECT,
        related_name="companies",
        limit_choices_to={"is_staff": True},
        null=True,
        blank=True,
    )
    with_nds = models.BooleanField("С НДС", default=False)

    # Contacts
    email = models.EmailField("Электронная почта", default="", blank=True)
    phone = PhoneNumberField("Номер телефона", db_index=True)

    # ДОБАВИЛ ДЛЯ ПОДПИСОК
    # Subscribe
    # subscribe = models.ForeignKey(
    #    'Subscribe',
    #    verbose_name="Подписка",
    #    on_delete=models.PROTECT,
    #    related_name="companies",
    #    null=True,
    #    blank=True,
    # )

    class Meta:
        verbose_name = "Компания"
        verbose_name_plural = "Компании"
        db_table = "companies"


class CompanyDocumentType(models.IntegerChoices):
    CHARTER = 1, "Устав"
    REQUISITES = 2, "Реквизиты"
    INN = 3, "ИНН"


class CompanyDocument(BaseModel):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    doc_type = get_field_from_choices(
        "Тип документа", CompanyDocumentType, null=True, blank=True
    )
    file = models.FileField("Документ", upload_to=company_storage)
    comment = models.CharField(
        "Комментарий", max_length=64, default="", blank=True
    )

    class Meta:
        verbose_name = "Документ компании"
        verbose_name_plural = "Документы компаний"
        db_table = "company_documents"


class CompanyRecyclablesActionType(models.IntegerChoices):
    BUY = 1, "Покупаю"
    SELL = 2, "Продаю"


class CompanyRecyclables(BaseModel):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="recyclables",
    )
    recyclables = models.ForeignKey(
        "product.Recyclables",
        verbose_name="Вторсырье",
        on_delete=models.PROTECT,
    )
    action = get_field_from_choices(
        "Действие",
        CompanyRecyclablesActionType,
        default=CompanyRecyclablesActionType.BUY,
    )
    monthly_volume = models.FloatField("Примерный ежемесячный объем")
    price = AmountField("Цена")

    class Meta:
        verbose_name = "Тип вторсырья компании"
        verbose_name_plural = "Типы вторсырья компаний"
        db_table = "company_recyclables"


class ActivityType(models.IntegerChoices):
    SUPPLIER = 1, "Поставщик"
    PROCESSOR = 2, "Переработчик"
    BUYER = 3, "Покупатель"


class RecyclingCollectionType(BaseNameModel):
    activity = get_field_from_choices("Вид деятельности", ActivityType)
    color = ColorField(default="#FF0000")

    class Meta:
        verbose_name = "Тип сбора/переработки"
        verbose_name_plural = "Типы сбора/переработки"
        db_table = "recycling_collection_types"
        unique_together = ("name", "activity")


class CompanyAdvantage(BaseNameModel):
    activity = get_field_from_choices("Вид деятельности", ActivityType)

    class Meta:
        verbose_name = "Преимущество компании"
        verbose_name_plural = "Преимущества компании"
        db_table = "company_advantages"
        unique_together = ("name", "activity")


class CompanyActivityType(BaseModel):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="activity_types",
    )
    activity = get_field_from_choices("Вид деятельности", ActivityType)
    rec_col_types = models.ManyToManyField(
        "company.RecyclingCollectionType",
        verbose_name="Тип сбора/переработки",
        blank=True,
    )
    advantages = models.ManyToManyField(
        "company.CompanyAdvantage",
        verbose_name="Преимущества компании",
        blank=True,
    )

    class Meta:
        verbose_name = "Виды деятельности компании"
        verbose_name_plural = "Виды деятельности компаний"
        db_table = "company_activity_types"
        # unique_together = ("company", "activity")


class ContactType(models.IntegerChoices):
    PHONE = 1, "Телефон"
    EMAIL = 2, "Электронная почта"
    WHATSAPP = 3, "Whatsapp"
    TELEGRAM = 4, "Telegram"


class CompanyAdditionalContact(BaseModel):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    contact_type = get_field_from_choices("Тип", ContactType)
    value = models.CharField("Контакт", max_length=32)
    comment = models.TextField("Комментарий", default="", blank=True)

    def __str__(self):
        return self.value

    class Meta:
        verbose_name = "Контакт компании"
        verbose_name_plural = "Контакты компаний"
        db_table = "company_contacts"


class CompanyVerificationRequestStatus(models.IntegerChoices):
    NEW = 1, "Новая"
    VERIFIED = 2, "Проверенная"
    RELIABLE = 3, "Надежная"
    DECLINE = 4, "Отклонена"


class CompanyVerificationRequest(BaseModel):
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="verifications",
    )
    employee = models.ForeignKey(
        User,
        verbose_name="Сотрудник",
        on_delete=models.CASCADE,
        default=get_current_user_id,
        related_name="verifications",
    )
    status = get_field_from_choices(
        "Статус",
        CompanyVerificationRequestStatus,
        default=CompanyVerificationRequestStatus.NEW,
    )
    comment = models.TextField("Комментарий", default="", blank=True)
    # для отслеживания изменений в полях модели.
    # FieldTracker позволяет запрашивать изменения
    # в полях с момента последнего сохранения экземпляра модели.
    status_tracker = FieldTracker(fields=["status"])

    class Meta:
        verbose_name = "Заявка на верификацию"
        verbose_name_plural = "Заявки на верификацию"
        db_table = "company_verification_requests"
        get_latest_by = "-created_at"
        ordering = ["-created_at"]

    def save(
            self,
            force_insert=False,
            force_update=False,
            using=None,
            update_fields=None,
    ):
        created = False
        if self.pk is None:  # если нет pk, то есть нет этого экземпляра (при выборе статуса верификации)
            created = True

        # delete previously created unprocessed requests
        # удалять ранее созданные необработанные запросы
        if created:  # если статус верификации выбран и его хотят изменить
            self.company.verifications.filter(
                status=CompanyVerificationRequestStatus.NEW
            ).delete()  # тогда берётся эта конкретная компания и у неё удаляется статус "Новая"

        company_changed = False
        employee_changed = False
        status_changed = self.status_tracker.changed()  # список полей подвергшихся изменению
        # если статус поменялся, то меняется статус компании и статус сотрудника (employee)
        if status_changed:
            if self.status == CompanyVerificationRequestStatus.VERIFIED:
                self.company.status = CompanyStatus.VERIFIED
                self.employee.status = UserStatus.VERIFIED
                company_changed = employee_changed = True

                verification_status_changed.send_robust(
                    self.__class__, instance=self
                )

            if self.status == CompanyVerificationRequestStatus.RELIABLE:
                self.company.status = CompanyStatus.RELIABLE
                company_changed = True

                verification_status_changed.send_robust(
                    self.__class__, instance=self
                )

                if self.employee.status == UserStatus.NOT_VERIFIED:
                    self.employee.status = UserStatus.VERIFIED
                    employee_changed = True

        if company_changed:
            self.company.save()
        if employee_changed:
            self.employee.save()

        super().save(force_insert, force_update, using, update_fields)

    def get_absolute_url(self):
        return reverse("company_verification-detail", kwargs={"pk": self.pk})


class Proposal(BaseModel):
    sender_company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="proposals",
    )

    special_id = models.CharField(
        max_length=255
    )

    companies = models.ManyToManyField(
        "company.Company",
        verbose_name="Компании из рассылок",
        blank=True,
        related_name="companies",
    )

    applications = models.ManyToManyField(
        "exchange.RecyclablesApplication",
        verbose_name="Заявки из рассылок",
        blank=True,
        related_name="applications",

    )

    class Meta:
        verbose_name = "Предложение"
        verbose_name_plural = "Предложения"
        db_table = "proposals"


class EquipmentProposal(BaseModel):
    sender_company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.CASCADE,
        related_name="equipment_proposals",
    )

    special_id = models.CharField(
        max_length=255
    )

    companies = models.ManyToManyField(
        "company.Company",
        verbose_name="Компании из рассылок",
        blank=True,
        related_name="equipments_companies",
    )

    applications = models.ManyToManyField(
        "exchange.EquipmentApplication",
        verbose_name="Заявки из рассылок",
        blank=True,
        related_name="equipments_applications",

    )

    class Meta:
        verbose_name = "Предложение по оборудованию"
        verbose_name_plural = "Предложения по оборудованию"
        db_table = "equipments_proposals"


class SubscribesLevels(models.IntegerChoices):
    ECONOMY = 1, "Эконом"
    STANDARD = 2, "Стандартный"
    EXTENDED = 3, "Расширенный"
    ABSOLUTE = 4, "Абсолют"


class SubscribesPeriod(models.IntegerChoices):
    MONTH = 1, "Месяц"
    THREE_MONTHS = 2, "3 Месяца"
    SIX_MONTHS = 3, "6 Месяцев"
    YEAR = 4, "Год"


class Subscribe(BaseNameDescModel):
    companies = models.ManyToManyField(
        "company.Company",
        through='SubscribesCompanies',
        verbose_name="Подписки компаний",
        blank=True,
        related_name="companies_subscribes",
    )

    level = get_field_from_choices(
        'Подписки',
        SubscribesLevels,
        default=SubscribesLevels.ECONOMY
    )

    counter = models.IntegerField(
        verbose_name="кол-во заявок",
        default=0
    )

    staff_count = models.PositiveSmallIntegerField(
        verbose_name="кол-во сотрудников",
        default=0
    )

    period = get_field_from_choices(
        'Период подписки',
        SubscribesPeriod,
        default=SubscribesPeriod.MONTH
    )

    price = models.FloatField(
        'Цена подписки',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"
        db_table = "subscribes"


class SubscribesCompanies(BaseModel):
    subscribe = models.ForeignKey(Subscribe, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    time_end = models.DateTimeField(verbose_name="Дата окончания подписки")
    time_begin = models.DateTimeField(verbose_name="Дата начала подписки")
    payment_number = models.CharField(verbose_name="Номер платежа", max_length=255, null=True, blank=True)
    payment_access = models.BooleanField(default=False, verbose_name="Успешность платежа", null=True, blank=True)
