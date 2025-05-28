from decimal import Decimal

from pydantic import BaseModel


class CompanyManager(BaseModel):
    name: str
    post: str


class CompanyState(BaseModel):
    status: str
    code: str | None = None
    actuality_date: int
    registration_date: int
    liquidation_date: int | None = None


class CompanyOpf(BaseModel):
    type: str
    code: str
    full: str
    short: str


class CompanyName(BaseModel):
    full_with_opf: str
    short_with_opf: str
    latin: str | None = None
    full: str
    short: str | None = None


class AddressDetail(BaseModel):
    postal_code: str | None = None
    country: str
    federal_district: str | None = None

    region: str | None = None
    region_type: str | None = None
    region_type_full: str | None = None

    area: str | None = None
    area_type: str | None = None
    area_type_full: str | None = None

    city: str | None = None
    city_type: str | None = None
    city_type_full: str | None = None
    city_area: str | None = None

    city_district: str | None = None
    city_district_type: str | None = None
    city_district_type_full: str | None = None

    settlement: str | None = None
    settlement_type: str | None = None
    settlement_type_full: str | None = None

    street: str | None = None
    street_type: str | None = None
    street_type_full: str | None = None

    house: str | None = None
    house_type: str | None = None
    house_type_full: str | None = None

    geo_lat: Decimal = None
    geo_lon: Decimal = None


class CompanyAddress(BaseModel):
    value: str
    unrestricted_value: str
    invalidity: str | None = None
    data: AddressDetail


class Person(BaseModel):
    surname: str
    name: str
    patronymic: str | None = None
    gender: str | None = None
    source: str | None = None
    qc: str | None = None


class CompanyData(BaseModel):
    kpp: str | None = None
    capital: str | None = None
    invalid: str | None = None
    fio: Person = None
    management: CompanyManager = None
    founders: str | None = None
    managers: str | None = None
    predecessors: str | None = None
    successors: str | None = None
    branch_type: str | None = None
    branch_count: int | None = None
    source: str | None = None
    qc: str | None = None
    hid: str | None = None
    type: str | None = None
    state: CompanyState
    opf: CompanyOpf
    name: CompanyName
    inn: str
    ogrn: str
    okpo: str | None = None
    okato: str | None = None
    oktmo: str | None = None
    okogu: str | None = None
    okfs: str | None = None
    okved: str
    okveds: str | None = None
    address: CompanyAddress
    phones: str | None = None
    emails: str | None = None
    ogrn_date: int
    okved_type: str | None = None
    employee_count: int | None = None
