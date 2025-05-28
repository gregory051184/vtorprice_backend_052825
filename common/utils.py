import json
import sys

from _decimal import Decimal

from django.conf import settings
from django.http import HttpRequest
from django.template import RequestContext
from rest_framework.settings import api_settings


def str2bool(v: str) -> bool:
    if v.lower() in ("yes", "true", "t", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "0"):
        return False
    raise ValueError("Unexpected boolean string")


def print_sql(sql, ret=False):
    """Print formatted sql (for debug)"""
    try:
        import sqlparse
    except ImportError:
        sqlparse = None

    try:
        import pygments.formatters
        import pygments.lexers
    except ImportError:
        pygments = None

    raw_sql = str(sql)

    if sqlparse:
        raw_sql = sqlparse.format(
            raw_sql, reindent_aligned=True, truncate_strings=500
        )

    if pygments:
        raw_sql = pygments.highlight(
            raw_sql,
            pygments.lexers.get_lexer_by_name("sql"),
            pygments.formatters.TerminalFormatter(),
        )

    if not ret:
        print(raw_sql)
        return True

    return raw_sql


"""
Current request
"""


def get_current_request():
    """
    Get the current request using introspection.

    Be careful when getting request.user because you can get a recursion
    if this code will be used in User manager. You need override ModelBackend.get_user:
        def get_user(self, user_id):
            user = UserModel.custom_manager.get(pk=user_id)

    custom_manager - manager without calling get_current_request()
    """
    request = None
    frame = sys._getframe(1)  # sys._getframe(0).f_back

    while frame:
        # check the instance of each funtion argument
        for arg in frame.f_code.co_varnames[: frame.f_code.co_argcount]:
            request = frame.f_locals[arg]

            if isinstance(request, HttpRequest):
                break

            # from template tag
            if isinstance(request, RequestContext):
                request = request.request
                break
        else:
            frame = frame.f_back
            continue

        break

    return request if isinstance(request, HttpRequest) else None


def get_current_user():
    """
    Get current user from request.

    Don't forget to check if you want to get an authorized user:
        if user and user.is_authenticated:
            ...
    """
    request = get_current_request()
    return getattr(request, "user", None)


def get_current_user_id():
    """Get current user id"""
    user = get_current_user()
    return user.pk if user and user.is_authenticated else None


# возвращает условий поиска в виде списка строк
def get_search_terms_from_request(request):
    """
    Search terms are set by a ?search=... query parameter,
    and may be comma and/or whitespace delimited.
    """
    search_param = api_settings.SEARCH_PARAM
    params = request.query_params.get(search_param, "")
    params = params.replace("\x00", "")  # strip null characters
    params = params.replace(",", " ")
    return params.split()


# Группирует queryset на основе какого-либо поля
def get_grouped_qs(qs, field):
    """
    Groups queryset by field

    :param qs: a queryset to be grouped
    :param field: str: grouping field
    :return: grouped dict, f.e.: {"group_1": [obj11, obj12,..], "group_2": [obj21, obj22,...]}
    """
    group_map = {}

    for obj in qs:
        f = getattr(obj, field)
        if f in group_map:
            group_map[f].append(obj)
        else:
            group_map[f] = [obj]

    return group_map


def get_nds_tax() -> int:
    return settings.NDS_VALUE


def get_nds_amount(amount):
    nds = get_nds_tax()
    divider = 100 + nds
    return amount / divider * nds


def subtract_percentage(amount, percent):
    return amount - (amount / 100 * percent)


def generate_random_sequence(length: int = 8):
    """
    Генерация последовательности заданной длины
    """
    import string, random

    characters = string.ascii_uppercase + string.digits
    pin = "".join(random.choice(characters) for i in range(length))

    return pin


class DecimalEncoder(json.JSONEncoder):
    """
    Because default encoder can't encode Decimal, we should use custom encoder to do it.
    Used code from: https://stackoverflow.com/a/52319674
    """

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)


MONTH_MAPPING = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}
