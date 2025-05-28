# Create your models here.
from bulk_update_or_create import BulkUpdateOrCreateQuerySet
from django.conf import settings
from django.db import models
from django.db.models import Count, Q, Max
from django.urls import reverse

from common.models import BaseModel, BaseNameModel
from user.models import UserRole


class ChatsQuerySet(BulkUpdateOrCreateQuerySet, models.QuerySet):
    def annotate_unread_messages(self, user, *args, **kwargs):
        return self.annotate(
            unread_count=Count(
                "messages",
                filter=(
                    Q(messages__is_read=False) & ~Q(messages__author=user)
                ),
            )
        )

    def annotate_latest_message(self, *args, **kwargs):
        return self.annotate(latest_created_at=Max("messages__created_at"))

    def filter_user_chats(self, user):
        if user.role == UserRole.COMPANY_ADMIN:
            return self.__filter_for_company_admin(user)
        if user.role == UserRole.LOGIST:
            return self.__filter_for_logist(user)
        return self

    def __filter_for_company_admin(self, user):
        return self.filter(
            Q(deal__buyer_company=user.company)
            | Q(deal__supplier_company=user.company)
            | Q(equipment_deal__buyer_company=user.company)
            | Q(equipment_deal__supplier_company=user.company)
            | Q(logisticsoffer__transportapplication__created_by__company=user.company)
            | Q(special_app__companies__id=user.company.id)
        )

    def __filter_for_logist(self, user):
        return self.filter(logisticsoffer__logist=user)


class Chat(BaseNameModel):
    class Meta:
        db_table = "chats"
        verbose_name = "Чат"
        verbose_name_plural = "Чаты"

    objects = ChatsQuerySet.as_manager()

    def get_absolute_url(self):
        return reverse("chats-detail", kwargs={"pk": self.pk})


class Message(BaseModel):
    chat = models.ForeignKey(
        Chat, on_delete=models.CASCADE, related_name="messages"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    content = models.TextField()
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        db_table = "chat_messages"
        verbose_name = "Сообщение чата"
        verbose_name_plural = "Сообщения чата"

    def get_absolute_url(self):
        return reverse(
            "messages", kwargs={"chat_pk": self.chat.pk, "pk": self.pk}
        )
