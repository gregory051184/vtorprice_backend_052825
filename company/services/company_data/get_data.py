import logging
from typing import Union

from django.conf import settings
from dadata import Dadata

from company.models import Company, City
from company.services.company_data.models import CompanyData, CompanyName, CompanyAddress, AddressDetail

log = logging.getLogger(__name__)


# возвращает список компаний найденных через сервис dadata
def get_companies_data(query: str) -> Union[list[CompanyData], None]:
    """
    Get data about the companies by IIN or name from the DaData service
    :param query: string containing INN or company name
    :return: list objects of CompanyData model
    """

    dadata = Dadata('8118fbfe3e47992be56928944189d122141017b9')  # (settings.DADATA_API_KEY)

    result = dadata.suggest("party", query)
    companies = []

    for item in result:
        data = item.get("data", None)

        if data is None:
            log.exception("DaData -- Incorrect data format")
            return None

        companies.append(CompanyData(**data))

# Удалить
# company_name_1 = CompanyName
# company_name_1.short_with_opf = 'МММ'
#
# company_address_detail_1 = AddressDetail
# company_address_detail_1.city = 'Сызрань'
# company_address_detail_1.geo_lon = 34.856
# company_address_detail_1.geo_lat = 134.854
#
# company_address_1 = CompanyAddress
# company_address_1.unrestricted_value = 'ул. Ульяновская'
# company_address_1.data = AddressDetail
#
# companies = []
# company_1 = CompanyData
#
# company_1.name = company_name_1
# company_1.inn = '6000000002'
# company_1.address = company_address_1
#
# print(company_1)
# c = [
#    {
#        'name': {
#            'short_with_opf': 'МММ'
#        },
#        'inn': '6000000002',
#        'address': {
#            'unrestricted_value': 'ул.',
#            'data': {
#                'city': 'Сызрань',
#                'geo_lat': 34.856,
#                'geo_lon': 134.854
#            }
#        }
#    }
# ]
# companies.append(company_1)
    return companies


# Работает для поиска компаний в том числе и при регистрации компании!!!
# TODO: Протестировать функцию
def get_companies(query: str):  # -> Union[list[Company], None]:
    """
    Gets a list of company objects by name or TIN number

    :param query: string containing INN or company name
    :return: list objects of Company model
    """
    # возвращает данные о компании/компаниях из сервиса dadata.ru
    companies_data = get_companies_data(query)

    companies = []

    cities_to_update = []  # for bulk update or create
    cities_names = []  # for getting list of cities from db
    city_company_map = (
        {}
    )  # for the subsequent connection of the company with the city

    # prepare data
    for company_data in companies_data:

        city_name = (
                company_data.address.data.city
                or company_data.address.data.settlement
        )
        cities_names.append(city_name)
        cities_to_update.append(City(name=city_name))
        company = Company(
            name=company_data.name.short_with_opf,
            inn=company_data.inn,
            address=company_data.address.unrestricted_value,
            latitude=company_data.address.data.geo_lat,
            longitude=company_data.address.data.geo_lon,
        )

        if city_name in city_company_map:
            city_company_map[city_name].append(company)
        else:
            city_company_map[city_name] = [company]

    # to avoid multiple queries to the database, we carry out bulk update or create cities
    City.objects.bulk_update_or_create(
        cities_to_update, ["name"], match_field="name"
    )  # Почему не определяется регион при создании экзепляра города
    # Но в company_data/models.py есть возможность извлечь регион!

    cities = City.objects.filter(name__in=cities_names)

    # rel cities with companies
    # связывает компанию с городом
    for city in cities:
        city_companies = city_company_map[city.name]
        for company in city_companies:
            company.city = city
            companies.append(company)

    return companies
