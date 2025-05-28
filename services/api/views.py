from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg import openapi as api

from company.models import City
from config import settings
from services.models import DeliveryCost
from services.validators import validate_logistics_coordinates
from services.yandex_geo import YandexGeocoderClient
from config.settings import YANDEX_GEOCODER_API_KEY

geocoder_client = YandexGeocoderClient(YANDEX_GEOCODER_API_KEY)


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        api.Parameter(
            "raw_address",
            api.IN_QUERY,
            type=api.TYPE_STRING,
            description="Адрес для поиска",
        ),
        api.Parameter(
            "num",
            api.IN_QUERY,
            type=api.TYPE_INTEGER,
            description="Количество адресов для возврата(не больше 100)",
            required=False,
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def yandex_geocoder(request):
    raw_address = request.query_params.get("raw_address")
    num = int(request.query_params.get("num", 10))
    if num > 100:
        raise ValidationError("You can't get more than 100 addresses")

    addresses = geocoder_client.get_addresses(raw_address, num)
    addresses_dict = list(map(lambda x: x.dict(), addresses))

    return Response(addresses_dict)


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        api.Parameter(
            "lat_from",
            api.IN_QUERY,
            type=api.TYPE_NUMBER,
            description="Широта отправления",
            required=True,
        ),
        api.Parameter(
            "lon_from",
            api.IN_QUERY,
            type=api.TYPE_NUMBER,
            description="Долгота отправления",
            required=True,
        ),
        api.Parameter(
            "lat_to",
            api.IN_QUERY,
            type=api.TYPE_NUMBER,
            description="Широта прибытия",
            required=True,
        ),
        api.Parameter(
            "lon_to",
            api.IN_QUERY,
            type=api.TYPE_NUMBER,
            description="Долгота прибытия",
            required=True,
        ),
    ],
)
@api_view(["GET"])
def approx_price(request):
    """Ожидается набор координат по типу: ?lat_from=30&lon_from=20&lat_to=40&lon_to=50"""

    departure_coordinates = (
        request.query_params.get("lat_from"),
        request.query_params.get("lon_from"),
    )
    delivery_coordinates = (
        request.query_params.get("lat_to"),
        request.query_params.get("lon_to"),
    )

    validate_logistics_coordinates(
        departure_coordinates + delivery_coordinates
    )

    delivery_data = DeliveryCost.from_coordinates(
        departure_coordinates, delivery_coordinates, settings.PRICE_PER_KM
    )
    return Response(delivery_data.dict())


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        api.Parameter(
            "delivery_city_pk",
            api.IN_QUERY,
            type=api.TYPE_NUMBER,
            description="Город отправления",
            required=True,
        ),
        api.Parameter(
            "shipping_city_pk",
            api.IN_QUERY,
            type=api.TYPE_NUMBER,
            description="Город доставки",
            required=True,
        ),
    ],
)
@api_view(["GET"])
def approximate_price_using_cities(request):
    cities_qs = City.objects.all()
    delivery_city_pk, shipping_city_pk = request.query_params.get(
        "delivery_city_pk"
    ), request.query_params.get("shipping_city_pk")

    delivery_city, shipping_city = get_object_or_404(
        cities_qs, pk=delivery_city_pk
    ), get_object_or_404(cities_qs, pk=shipping_city_pk)

    delivery_city_data = geocoder_client.get_coordinates_from_city(
        delivery_city
    )
    shipping_city_data = geocoder_client.get_coordinates_from_city(
        shipping_city
    )

    delivery_data = DeliveryCost.from_coordinates(
        (delivery_city_data.latitude, delivery_city_data.longitude),
        (shipping_city_data.latitude, delivery_city_data.longitude),
        settings.PRICE_PER_KM,
    )
    return Response(delivery_data.dict())


