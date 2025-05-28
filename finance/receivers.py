from django.dispatch import receiver

from exchange.models import RecyclablesDeal
from exchange.signals import deal_completed
from finance.models import InvoicePayment


@receiver(deal_completed, sender=RecyclablesDeal)
def handle_completed_deal(sender, instance, **kwargs):
    buyer_company = instance.buyer_company
    supplier_company = instance.supplier_company
    # плата за сделку равняется кол-ву перевезенных килограммов
    amount = instance.weight
    to_create = []
    for company in [buyer_company, supplier_company]:
        to_create.append(
            InvoicePayment(amount=amount, company=company, deal=instance)
        )
    InvoicePayment.objects.bulk_create(to_create)
