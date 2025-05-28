from bulk_update_or_create import BulkUpdateOrCreateQuerySet
from django.db import models

from common.model_fields import LatitudeField, LongitudeField


class BaseModelManager(models.Manager):
    def get_queryset(self):
        return (
            super(BaseModelManager, self)
            .get_queryset()
            .filter(is_deleted=False)
        )


class BaseModel(models.Model):
    is_deleted = models.BooleanField(
        verbose_name="Помечен как удаленный", default=False
    )
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    # Переопределяем менежер objects
    objects = BulkUpdateOrCreateQuerySet.as_manager()

    class Meta:
        abstract = True


class BaseNameModel(BaseModel):
    name = models.CharField(
        verbose_name="Название", max_length=1024, db_index=True
    )

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class BaseNameDescModel(BaseNameModel):
    description = models.TextField("Описание", default="", blank=True)

    class Meta:
        abstract = True


class AddressFieldsModelMixin(models.Model):
    """
    Abstract model with location coordinates, city and address fields
    """

    city = models.ForeignKey(
        "company.City",
        verbose_name="Город",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    address = models.CharField(
        "Адрес", max_length=1024, default="", blank=True, null=True
    )
    latitude = LatitudeField(blank=True, null=True)
    longitude = LongitudeField(blank=True, null=True)

    class Meta:
        abstract = True


class DeliveryFieldsModelMixin(models.Model):
    """
    Abstract model with location coordinates, city and address fields from to
    """

    shipping_address = models.CharField(
        "Адрес отгрузки", max_length=1024, default="", blank=True
    )
    shipping_latitude = LatitudeField(
        verbose_name="Широта адреса отгрузки", blank=True, null=True
    )
    shipping_longitude = LongitudeField(
        verbose_name="Долгота адреса отгрузки", blank=True, null=True
    )

    delivery_address = models.CharField(
        "Адрес доставки", max_length=1024, default="", blank=True
    )
    delivery_latitude = LatitudeField(
        verbose_name="Широта адреса доставки", blank=True, null=True
    )
    delivery_longitude = LongitudeField(
        verbose_name="Долгота адреса доставки", blank=True, null=True
    )

    class Meta:
        abstract = True
