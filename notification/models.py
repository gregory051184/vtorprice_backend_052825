from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from common.models import BaseNameModel


User = get_user_model()


class Notification(BaseNameModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        verbose_name="Компания",
        null=True,
    )
    content_type = models.ForeignKey(
        ContentType, verbose_name="Тип контента", on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    is_read = models.BooleanField(default=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name="Пользователь", null=True
    )

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        db_table = "notifications"

    @staticmethod
    def create_notification(company, content_object, message):
        return Notification.objects.create(
            company=company, content_object=content_object, name=message
        )
