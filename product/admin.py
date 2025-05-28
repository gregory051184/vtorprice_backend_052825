from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django_mptt_admin.admin import DjangoMpttAdmin
from mptt.admin import TreeRelatedFieldListFilter

from common.admin import BaseModelAdmin
from product.models import (
    RecyclablesCategory,
    Recyclables,
    Equipment,
    EquipmentCategory,
)


@admin.register(RecyclablesCategory)
class RecyclablesCategoryAdmin(BaseModelAdmin, DjangoMpttAdmin):
    search_fields = ("name",)


# # TODO Remove later
#
# @admin.register(RecyclingCode)
# class RecyclingCodeAdmin(BaseModelAdmin):
#     search_fields = (
#         "name",
#         "gost_name",
#     )


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(BaseModelAdmin, DjangoMpttAdmin):
    search_fields = ("name",)


class RecyclablesCategoryFilter(AutocompleteFilter):
    title = "Категория вторсырья"
    field_name = "category"


class BaseProductModelAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "name",
        "description",
        "category",
    )
    list_select_related = ("category",)
    autocomplete_fields = ("category",)
    list_filter = (("category", TreeRelatedFieldListFilter),)


@admin.register(Recyclables)
class RecyclablesAdmin(BaseProductModelAdmin):
    # Declaration in base class causes autocomplete error:
    # (admin.E040) EquipmentAdmin must define "search_fields"
    search_fields = (
        "name",
        "category__name",
        # "recycling_code__name",
        # "recycling_code__gost_name",
    )


@admin.register(Equipment)
class EquipmentAdmin(BaseModelAdmin):
    # Declaration in base class causes autocomplete error:
    # (admin.E040) EquipmentAdmin must define "search_fields"
    search_fields = ("name", "category__name")
