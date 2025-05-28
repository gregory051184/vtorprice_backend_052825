from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class NotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notification"

    def ready(self):
        autodiscover_modules("receivers")
