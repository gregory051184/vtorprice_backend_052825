import logging
from typing import List, Dict

from requests import Session

from services.models import AddressData
from company.models import City
from config.settings import YANDEX_GEOCODER_BASE_URL

log = logging.getLogger(__name__)

from common.HTTPClient.client import BaseClient


class YandexGeocoderClient(BaseClient):
    _DEFAULT_BASE_URL = YANDEX_GEOCODER_BASE_URL

    def __init__(self, api_key, base_url=None, **kwargs):
        self.api_key = api_key
        self._session = Session()
        self.kwargs = kwargs or {}
        self.base_url = base_url or self._DEFAULT_BASE_URL

    def get_addresses(self, raw_addresses, addresses_to_return=10):
        raw_json = self._make_request(raw_addresses, addresses_to_return)
        return self._parse_response(raw_json)

    def get_coordinates_from_city(self, city: City):
        city_name = city.name
        if city.latitude and city.longitude:
            return AddressData(
                address=city_name,
                city=city.pk,
                latitude=city.latitude,
                longitude=city.longitude,
            )
        raw_json = self._make_request(city_name, 1)
        return self._parse_city_coordinates(raw_json, city.pk)

    def _parse_city_coordinates(self, response_body, city_pk):
        geo_object = response_body["response"]["GeoObjectCollection"][
            "featureMember"
        ][0]

        object_text = geo_object["GeoObject"]["metaDataProperty"][
            "GeocoderMetaData"
        ]["text"]

        object_lat, object_long = map(
            float, geo_object["GeoObject"]["Point"]["pos"].split()
        )

        return AddressData(
            address=object_text,
            longitude=object_long,
            latitude=object_lat,
            city=city_pk,
        )

    def _make_request(self, raw_adresses, addresses_to_return=10):
        log.info(
            f"Yandex geocoder request with address: {raw_adresses} and {addresses_to_return} addresses."
        )
        url = "/1.x/"
        params = {
            "apikey": self.api_key,
            "format": "json",
            "geocode": raw_adresses,
            "results": addresses_to_return,
        }
        return self._request(url=url, get_params=params)

    def _parse_response(self, response_body: Dict) -> List[AddressData]:
        geo_objects = response_body["response"]["GeoObjectCollection"][
            "featureMember"
        ]
        parsed_geo_objects: List[AddressData] = list()

        for geo_object in geo_objects:
            object_text = geo_object["GeoObject"]["metaDataProperty"][
                "GeocoderMetaData"
            ]["text"]

            object_long, object_lat = map(
                float, geo_object["GeoObject"]["Point"]["pos"].split()
            )

            city_id = self._get_city_id(geo_object)
            # Checking if city have been extracted from geocoder response, if no, than skip current address
            if not city_id:
                continue

            parsed_geo_objects.append(
                AddressData(
                    address=object_text,
                    longitude=object_long,
                    latitude=object_lat,
                    city=city_id,
                )
            )

        return parsed_geo_objects

    def _get_city_id(self, geo_object):
        address_components = geo_object["GeoObject"]["metaDataProperty"][
            "GeocoderMetaData"
        ]["Address"]["Components"]

        # In address_components we have a bunch of dicts with keys:
        # 'kind', 'name'
        # If kind == "locality", than it's a city
        # So, below we are trying to extract that city component
        city_component = list(
            filter(lambda x: x["kind"] == "locality", address_components)
        )
        # If we successfully extracted city component, then we can extract city name
        # And then we can get city id from DB
        city_name = city_component[0]["name"] if city_component else None
        if not city_name:
            return None

        # Возможны лаги работы с БД
        # TODO: оптимизировать поиск/создание кучи объектов
        city, created = City.objects.get_or_create(name=city_name)
        return city.pk
