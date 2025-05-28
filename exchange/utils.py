import datetime

from django.db.models.functions import TruncDay, TruncMonth
from rest_framework.exceptions import ValidationError

from exchange.models import UrgencyType, RecyclablesApplication


def get_recyclables_application_total_weight(
    application: RecyclablesApplication,
) -> float:
    if application.full_weigth:
        return application.full_weigth
    if application.urgency_type == UrgencyType.READY_FOR_SHIPMENT:
        total_weight = application.bale_count * application.bale_weight
    elif application.urgency_type == UrgencyType.SUPPLY_CONTRACT:
        total_weight = application.volume
    else:
        raise NotImplementedError

    return total_weight


def get_truncation_class(period: str):
    """
    Return datetime Truncation class based on given period
    For week and month we truncate by day
    For all other cases we truncate by month
    """
    if period in ("week", "month"):
        return TruncDay
    return TruncMonth


def get_lower_date_bound(period: str):
    now = datetime.datetime.today()
    if period == "week":
        return now - datetime.timedelta(weeks=1)
    if period == "month":
        return now - datetime.timedelta(days=31)
    if period == "year":
        return now - datetime.timedelta(days=365)
    return None


def validate_period(period: str):
    if period.lower() not in ("week", "month", "year", "all"):
        raise ValidationError(
            'Period must be "week", "month" or "year" or "all"'
        )
    return period.lower()
