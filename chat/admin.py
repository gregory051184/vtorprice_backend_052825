# Register your models here.
from django.contrib import admin

from chat.models import Chat, Message
from common.admin import BaseModelAdmin


@admin.register(Chat)
class ChatAdmin(BaseModelAdmin):
    list_display = ["id"]


@admin.register(Message)
class MessageAdmin(BaseModelAdmin):
    list_display = ["id", "author", "content"]
