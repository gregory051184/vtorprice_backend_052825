import datetime

from django.db.models import Q
from environs import Env

import uuid

from yookassa import Configuration, Payment

from company.models import SubscribesCompanies, Subscribe
from config.settings import YOOKASSA_TEST_SHOP_ID, YOOKASSA_AUTH_API_KEY_TEST
from exchange.models import SpecialApplication, SpecialApplicationPeriod, SpecialApps

env = Env()
env.read_env()

Configuration.account_id = int(YOOKASSA_TEST_SHOP_ID)
Configuration.secret_key = str(YOOKASSA_AUTH_API_KEY_TEST)


def create_payment(serializer_data):
    return_url = serializer_data.get('return_url')
    company = serializer_data.get('company_id')
    subscribe = serializer_data.get('subscribe_id')
    time_end = serializer_data.get('time_end')

    time_begin = serializer_data.get('time_begin')

    current_subscribe = Subscribe.objects.get(id=subscribe)

    if len(current_subscribe.name.split(' ')) == 1:
        end = datetime.date.today() + datetime.timedelta(days=30)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    elif int(current_subscribe.name.split('+')[1]) == 3:
        end = datetime.date.today() + datetime.timedelta(days=90)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    elif int(current_subscribe.name.split('+')[1]) == 6:
        end = datetime.date.today() + datetime.timedelta(days=180)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    elif int(current_subscribe.name.split('+')[1]) == 12:
        end = datetime.date.today() + datetime.timedelta(days=360)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    try:
        company_subscribe_exists = SubscribesCompanies.objects.get(~Q(is_deleted=1), company_id=company)
        if company_subscribe_exists:
            company_subscribe_exists.is_deleted = True
            company_subscribe_exists.save()
    except:
        pass

    company_subscribe = SubscribesCompanies.objects.create(
        subscribe_id=subscribe,
        company_id=company,
        time_end=time_end,
        time_begin=time_begin,
        payment_number=uuid.uuid4(),
        payment_access=False
    )

    payment = Payment.create({
        'amount': {
            'value': company_subscribe.subscribe.price,
            'currency': 'RUB',
        },
        'confirmation': {
            'type': 'redirect',
            'return_url': return_url,
        },
        'capture': True,
        'refundable': False,
        'description': f'Покупка подписки {company_subscribe.subscribe.name} {company_subscribe.subscribe.price} руб.',
    }, company_subscribe.payment_number)

    return payment.confirmation.confirmation_url


def create_payment_for_special_app(serializer_data):
    return_url = serializer_data.get('return_url')
    company = serializer_data.get('company_id')
    special_application = serializer_data.get('special_application_id')
    time_end = serializer_data.get('time_end')
    time_begin = serializer_data.get('time_begin')

    current_special_application = SpecialApplication.objects.get(id=special_application)

    if current_special_application.period == SpecialApplicationPeriod.DAY:
        end = datetime.date.today() + datetime.timedelta(days=1)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    if current_special_application.period == SpecialApplicationPeriod.TWO_DAYS:
        end = datetime.date.today() + datetime.timedelta(days=2)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    if current_special_application.period == SpecialApplicationPeriod.FOUR_DAYS:
        end = datetime.date.today() + datetime.timedelta(days=4)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    if current_special_application.period == SpecialApplicationPeriod.WEEK:
        end = datetime.date.today() + datetime.timedelta(days=7)
        time_end = str(end) + 'T' + time_end.split('T')[1]

    try:
        company_special_application_exists = SpecialApps.objects.get(~Q(is_deleted=1), company_id=company)
        if company_special_application_exists:
            company_special_application_exists.is_deleted = True
            company_special_application_exists.save()
    except:
        pass

    company_special_application = SpecialApps.objects.create(
        special_application_id=special_application,
        company_id=company,
        time_end=time_end,
        time_begin=time_begin,
        payment_number=uuid.uuid4(),
        payment_access=False
    )
    payment = Payment.create({
        'amount': {
            'value': company_special_application.special_application.period.price,
            # company_special_application.special_application.price,
            'currency': 'RUB',
        },
        'confirmation': {
            'type': 'redirect',
            'return_url': return_url,
        },
        'capture': True,
        'refundable': False,
        'description': f'Покупка специальной заявки на период {company_special_application.special_application.period} {company_special_application.special_application.price} руб.',
    }, company_special_application.payment_number)

    return payment.confirmation.confirmation_url
