from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from common.admin import BaseModelAdmin
from exchange.models import (
    RecyclablesApplication,
    ImageModel,
    RecyclablesDeal,
    UrgencyType,
    EquipmentApplication,
    EquipmentDeal,
    Review,
)


class ImageModelInline(GenericTabularInline):
    model = ImageModel
    extra = 1


class ReviewInline(GenericTabularInline):
    model = Review
    extra = 1


@admin.register(RecyclablesApplication)
class RecyclablesApplicationAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "company",
        "recyclables",
        "deal_type",
        "urgency_type",
        "with_nds",
        "city",
        "total_weight_property",
        "total_price_property",
        "status",
        "application_recyclable_status"
    )
    list_select_related = ("company", "recyclables")
    autocomplete_fields = ("company", "recyclables")
    list_filter = ("deal_type", "urgency_type", "with_nds", "status", "application_recyclable_status")
    search_fields = (
        "company__name",
        "company__inn",
        "recyclables__name",
    )
    inlines = [
        ImageModelInline,
    ]
    exclude = ["images"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate_total_weight()

    def total_weight_property(self, obj):
        return obj.total_weight

    total_weight_property.short_description = "Общий вес"

    def total_price_property(self, obj):
        return obj.total_price

    total_price_property.short_description = "Общая стоимость"


@admin.register(RecyclablesDeal)
class RecyclablesDealAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "deal_number",
        "status",
        "supplier_company",
        "buyer_company",
        "recyclables",
        "urgency_type",
        "with_nds",
        "weight",
        "total_price_property",
        "who_delivers",
    )
    list_select_related = (
        "supplier_company",
        "buyer_company",
        "application__recyclables",
        "application",
        "shipping_city",
        "delivery_city",
        "created_by",
    )
    autocomplete_fields = (
        "supplier_company",
        "buyer_company",
        "application",
        "created_by",
    )
    list_filter = (
        "application__urgency_type",
        "who_delivers",
        "with_nds",
        "status",
    )
    search_fields = (
        "supplier_company__name",
        "supplier_company__inn",
        "buyer_company__name",
        "buyer_company__inn",
        "application__recyclables__name",
        "deal_number",
    )
    inlines = (ReviewInline,)

    def recyclables(self, obj):
        return obj.application.recyclables.name

    recyclables.short_description = "Вторсырье"

    def urgency_type(self, obj):
        return UrgencyType(obj.application.urgency_type).label

    urgency_type.short_description = "Срочность"

    def total_price_property(self, obj):
        return obj.total_price

    total_price_property.short_description = "Общая стоимость"


@admin.register(EquipmentApplication)
class EquipmentApplicationAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "company",
        "equipment",
        "deal_type",
        "with_nds",
        "city",
        "price",
        "status",
    )
    list_select_related = ("company", "category", "equipment")
    autocomplete_fields = ("company", "category", "equipment")
    list_filter = ("deal_type", "with_nds", "status")
    search_fields = (
        "company__name",
        "company__inn",
        "equipment__name",
    )
    inlines = [
        ImageModelInline,
    ]
    exclude = ["images"]


@admin.register(EquipmentDeal)
class EquipmentDealAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "deal_number",
        "status",
        "supplier_company",
        "buyer_company",
        "equipment",
        "with_nds",
        "total_price_property",
        "who_delivers",
    )
    list_select_related = (
        "supplier_company",
        "buyer_company",
        "application__equipment",
        "application",
        "shipping_city",
        "delivery_city",
        "created_by",
    )
    autocomplete_fields = (
        "supplier_company",
        "buyer_company",
        "application",
        "created_by",
    )
    list_filter = (
        "who_delivers",
        "with_nds",
        "status",
    )
    search_fields = (
        "supplier_company__name",
        "supplier_company__inn",
        "buyer_company__name",
        "buyer_company__inn",
        "application__equipment__name",
        "deal_number",
    )
    inlines = (ReviewInline,)

    def equipment(self, obj):
        return obj.application.equipment.name

    equipment.short_description = "Оборудование"

    def total_price_property(self, obj):
        return obj.total_price

    total_price_property.short_description = "Общая стоимость"
