# Register your models here.
from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from common.admin import BaseModelAdmin
from exchange.models import DocumentModel
from logistics.models import (
    Contractor,
    TransportApplication,
    LogisticsOffer,
)


class DocumentModelInline(GenericTabularInline):
    model = DocumentModel
    extra = 1


@admin.register(Contractor)
class ContractorAdmin(BaseModelAdmin):
    list_display = ("id", "name", "created_by", "transport_owns_count")
    search_fields = ("name",)
    inlines = (DocumentModelInline,)
    list_select_related = ("created_by",)
    autocomplete_fields = ("created_by",)
    list_filter = ("contractor_type",)


class ShippingCityFilter(AutocompleteFilter):
    title = "Город отгрузки"
    field_name = "shipping_city"


class DeliveryCityFilter(AutocompleteFilter):
    title = "Город доставки"
    field_name = "delivery_city"


@admin.register(TransportApplication)
class TransportApplicationAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "sender",
        "recipient",
        "shipping_address",
        "delivery_address",
        "status",
    )
    autocomplete_fields = ("created_by",)
    search_fields = ("sender", "recipient")
    list_filter = ("status", ShippingCityFilter, DeliveryCityFilter)
    readonly_fields = ("created_at",)


@admin.register(LogisticsOffer)
class LogisticsOfferAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "logist",
        "amount",
        "application",
        "shipping_date",
        "contractor",
        "status",
    )

    autocomplete_fields = ("contractor",)
    search_fields = (
        "contractor",
        "logist",
    )
    list_select_related = ("contractor", "logist", "application")
