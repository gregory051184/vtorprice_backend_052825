"""
Subscribing to signals from other app models and creating notifications on their updates
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver

from chat.models import Message
from company.models import CompanyVerificationRequest
from company.signals import verification_status_changed
from exchange.models import (
    RecyclablesDeal,
    EquipmentDeal,
    RecyclablesApplication,
    EquipmentApplication,
)
from exchange.signals import (
    recyclables_deal_status_changed,
    application_status_changed,
)
from logistics.models import TransportApplication
from logistics.signals import transport_application_status_update
from notification.models import Notification
from user.models import UserRole, Favorite

User = get_user_model()


@receiver(post_save, sender=Message)
def handle_new_message(sender, instance: Message, created, **kwargs):
    if created and hasattr(instance.chat, "deal"):
        sender_company = instance.author.company
        receiver_company = (
            instance.chat.deal.supplier_company
            if sender_company == instance.chat.deal.buyer_company
            else instance.chat.deal.buyer_company
        )

        Notification.create_notification(
            receiver_company,
            instance,
            message=f"Новое сообщение в {instance.chat.name}",
        )


@receiver(post_save, sender=RecyclablesDeal)
def handle_new_recyclables_deal(
    sender, instance: RecyclablesDeal, created, **kwargs
):
    if created:
        company = instance.application.company
        Notification.create_notification(
            company,
            instance,
            message=f"Новая сделка по заявке {instance.application.pk}",
        )


@receiver(post_save, sender=EquipmentDeal)
def handle_new_equipment_deal(
    sender, instance: EquipmentDeal, created, **kwargs
):
    if created:
        company = instance.application.company
        Notification.create_notification(
            company,
            instance,
            message=f"Новая сделка по заявке {instance.application.pk}",
        )


@receiver(verification_status_changed, sender=CompanyVerificationRequest)
def handle_verification_status_change(
    sender, instance: CompanyVerificationRequest, **kwargs
):
    mapping_notification_id_to_name = {
        1: "Новая",
        2: "Проверенная",
        3: "Надежная",
        4: "Отклонена",
    }
    Notification.create_notification(
        instance.company,
        instance,
        message=f"Смена статуса заявки на верификацию: {mapping_notification_id_to_name.get(instance.status)}",
    )


@receiver(recyclables_deal_status_changed, sender=RecyclablesDeal)
def handle_recyclables_deal_status_change(
    sender, instance: RecyclablesDeal, **kwargs
):
    to_create = []
    new_status = kwargs.get("status")
    for company in (instance.supplier_company, instance.buyer_company):
        to_create.append(
            Notification(
                name=f"Смена статуса сделки {instance.deal_number} на {new_status}",
                company=company,
                content_object=instance,
            )
        )

    Notification.objects.bulk_create(to_create)


@receiver(transport_application_status_update, sender=TransportApplication)
def handle_transport_application_status_change(
    sender, instance: TransportApplication, **kwargs
):
    mapping_notification_id_to_name = {
        1: "Назначение логиста",
        2: "Машина загружена",
        3: "Машина выгружена",
        4: "Окончательная приемка",
        5: "Выполнена",
        6: "Отменена",
    }
    to_create = []
    status = kwargs.get("status")

    for user in [
        instance.created_by,
        instance.approved_logistics_offer.logist,
    ]:
        to_create.append(
            Notification(
                name=f"Смена статуса транспортной заявки {instance.pk} на {mapping_notification_id_to_name.get(status)}",
                user=user,
                content_object=instance,
            )
        )

    Notification.objects.bulk_create(to_create)


@receiver(post_save, sender=TransportApplication)
def handle_new_transport_application(
    sender, instance: TransportApplication, created, **kwargs
):
    if created:
        logists = User.objects.filter(role=UserRole.LOGIST)
        to_create = []
        for logist in logists:
            to_create.append(
                Notification(
                    user=logist,
                    content_object=instance,
                    name="Создана новая заявка на транспорт",
                )
            )

        Notification.objects.bulk_create(to_create)


@receiver(post_save, sender=RecyclablesApplication)
def handle_new_recyclables_application(
    sender, instance: RecyclablesApplication, created, **kwargs
):
    if not created:
        return

    company = instance.company
    company_content_type = ContentType.objects.get_for_model(company)
    users_to_notify = Favorite.objects.filter(
        content_type=company_content_type, object_id=company.pk
    ).values_list("user", flat=True)

    to_create = []
    for user in users_to_notify:
        to_create.append(
            Notification(
                name="Компания из вашего списка подписок создала заявку на вторсырье",
                user_id=user,
                content_object=instance,
            )
        )

    Notification.objects.bulk_create(to_create)


@receiver(post_save, sender=EquipmentApplication)
def handle_new_recyclables_application(
    sender, instance: EquipmentApplication, created, **kwargs
):
    if not created:
        return

    company = instance.company
    company_content_type = ContentType.objects.get_for_model(company)
    users_to_notify = Favorite.objects.filter(
        content_type=company_content_type, object_id=company.pk
    ).values_list("user", flat=True)

    to_create = []
    for user in users_to_notify:
        to_create.append(
            Notification(
                name="Компания из вашего списка подписок создала заявку на оборудование",
                user=user,
                content_object=instance,
            )
        )

    Notification.objects.bulk_create(to_create)


@receiver(application_status_changed, sender=RecyclablesApplication)
def handle_recyclables_application_status_change(
    sender, instance: RecyclablesApplication, **kwargs
):
    to_create = []
    kwargs.get("status")
    to_create.append(
        Notification(
            name=f"Смена статуса заявки на вторсырье {instance.pk}",
            company=instance.company,
            content_object=instance,
        )
    )

    Notification.objects.bulk_create(to_create)


@receiver(application_status_changed, sender=EquipmentApplication)
def handle_recyclables_equipment_status_change(
    sender, instance: EquipmentApplication, **kwargs
):
    to_create = []
    kwargs.get("status")
    to_create.append(
        Notification(
            name=f"Смена статуса заявки на оборудование {instance.pk}",
            company=instance.company,
            content_object=instance,
        )
    )

    Notification.objects.bulk_create(to_create)
