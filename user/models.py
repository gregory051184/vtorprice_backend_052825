import uuid

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from common.model_fields import get_field_from_choices
from common.models import BaseModel

def user_storage(instance, filename):
    ext = filename.split(".")[-1]
    uuid_filename = "{}.{}".format(uuid.uuid4(), ext)
    return f'user_storage/{instance.last_name}_{instance.first_name}_id_{instance.id}/{uuid_filename}'
    #return "user_storage/{0}".format(uuid_filename)


class CustomUserManager(UserManager):
    def _create_user(self, phone, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not phone:
            raise ValueError("The given phone must be set")
        email = self.normalize_email(email)
        user = self.model(phone=phone, email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, email, password, **extra_fields)

    def create_superuser(
        self, phone, email=None, password=None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(phone, email, password, **extra_fields)


class UserRole(models.IntegerChoices):
    SUPER_ADMIN = 1, "Супер-Администратор ВторПрайс"
    ADMIN = 2, "Администратор ВторПрайс"
    MANAGER = 3, "Менеджер ВторПрайс"
    LOGIST = 4, "Логист ВторПрайс"
    COMPANY_ADMIN = 5, "Владелец компании",
    COMPANY_STAFF = 6, "Сотрудник компании"


class UserStatus(models.IntegerChoices):
    NOT_VERIFIED = 1, "Не проверенный"
    VERIFIED = 2, "Проверенный"
    BLOCKED = 3, "Заблокированный"


class User(AbstractUser, BaseModel):
    # disable username field inheritance from AbstractUser model
    username = None

    # Names
    first_name = models.CharField("Имя", max_length=32, default="", blank=True)
    middle_name = models.CharField(
        "Отчество", max_length=32, default="", blank=True
    )
    last_name = models.CharField(
        "Фамилия", max_length=32, default="", blank=True, db_index=True
    )

    # Personal
    birth_date = models.DateField("Дата рождения", null=True, blank=True)

    # Contacts
    email = models.EmailField(
        "Электронная почта", blank=True, null=True, db_index=True
    )
    phone = PhoneNumberField("Номер телефона", unique=True, db_index=True)

    # Code for auth
    code = models.CharField(
        "Код для верификации по номеру телефона",
        max_length=4,
        null=True,
        blank=True,
    )

    #company_staff = models.ForeignKey(
    #    "company.Company",
    #    verbose_name="Сотрудники",
    #    on_delete=models.PROTECT,
    #    related_name="staff_company",
    #    #limit_choices_to={"role": UserRole.COMPANY_ADMIN},
    #    null=True,
    #    blank=True,
    #)

    role = get_field_from_choices(
        "Роль", UserRole, default=UserRole.COMPANY_ADMIN
    )
    position = models.CharField(
        "Должность", max_length=128, default="", blank=True
    )
    status = get_field_from_choices(
        "Статус", UserStatus, default=UserStatus.NOT_VERIFIED
    )
    company = models.ForeignKey(
        "company.Company",
        verbose_name="Компания",
        on_delete=models.PROTECT,
        related_name="employees",
        null=True,
        blank=True,
    )

    image = models.ImageField(
        "Фото/логотип", upload_to=user_storage, null=True, blank=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "phone"

    objects = CustomUserManager()

    def get_short_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_full_name(self):
        """
        Return the first_name plus the last_name plus the middle_name, with a space in between.
        """
        full_name = f"{self.last_name} {self.first_name} {self.middle_name}"
        return full_name.strip()

    def __str__(self):
        if self.first_name and self.last_name:
            return self.get_short_name()
        return str(self.phone)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        db_table = "users"
        ordering = ["first_name", "last_name"]


class Favorite(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    class Meta:
        db_table = "favorite"
