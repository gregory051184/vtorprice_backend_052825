from django.core.exceptions import ObjectDoesNotExist

from company.models import SubscribesCompanies
from exchange.models import SpecialApps


def payment_acceptance(response):
    try:
        table = SubscribesCompanies.objects.get(
            id=response['object']['metadata']['table_id']
        )
    except ObjectDoesNotExist:
        return False

    if response['event'] == 'payment.succeeded':
        table.payment_access = True
        table.save()

    elif response['event'] == 'payment.canceled':
        table.delete()

    return True


def payment_acceptance_special_application(response):
    try:
        table = SpecialApps.objects.get(
            id=response['object']['metadata']['table_id']
        )
    except ObjectDoesNotExist:
        return False

    if response['event'] == 'payment.succeeded':
        table.payment_access = True
        table.save()

    elif response['event'] == 'payment.canceled':
        table.delete()

    return True
