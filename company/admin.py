from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import render
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from django import forms
from common.admin import BaseModelAdmin
from company.models import (
    Company,
    CompanyDocument,
    CompanyRecyclables,
    CompanyAdditionalContact,
    CompanyVerificationRequest,
    RecyclingCollectionType,
    CompanyAdvantage,
    ActivityType,
    CompanyActivityType,
    City,
    Region,
    CompanyStatus,
    Subscribe, Proposal, SubscribesLevels, SubscribesPeriod, District
)
from exchange.models import (
    RecyclablesApplication,
    ApplicationStatus,
    DealType,
    UrgencyType, SpecialApplication,
)
from product.models import RecyclablesCategory, Recyclables

import logging

log = logging.getLogger(__name__)


class CompanyDocumentInline(admin.StackedInline):
    model = CompanyDocument
    extra = 0


class CompanyRecyclablesInline(admin.StackedInline):
    model = CompanyRecyclables
    extra = 0


class CompanyAdditionalContactInline(admin.StackedInline):
    model = CompanyAdditionalContact
    extra = 0


class CompanyVerificationRequestInline(admin.StackedInline):
    model = CompanyVerificationRequest
    extra = 0


class CompanyActivityTypeInline(admin.StackedInline):
    model = CompanyActivityType
    extra = 0


# class SubscribesLevelsInline(admin.StackedInline):
#    model = SubscribesLevels
#    extra = 0
#
#
# class SubscribesPeriodInline(admin.StackedInline):
#    model = SubscribesPeriod
#    extra = 0


class CompanyResource(resources.ModelResource):
    class Meta:
        model = Company
        fields = (
            "name",
            "inn",
            "phone",
            "city",
            "address",
            "latitude",
            "longitude",
        )
        import_id_fields = ("inn",)

    address = fields.Field(column_name="Адрес Компании", attribute="address")
    name = fields.Field(column_name="Название компании", attribute="name")
    inn = fields.Field(column_name="inn", attribute="inn")
    phone = fields.Field(column_name="Рабочий телефон", attribute="phone")

    def __parse_number(self, phone_number: str):
        if phone_number.startswith("8"):
            phone_number = "+7" + phone_number[1:]
        if phone_number.startswith("7"):
            phone_number = "+" + phone_number
        if phone_number.startswith("9"):
            phone_number = "+7" + phone_number

        return phone_number

    def __parse_price(self, price: str):
        if price is None or price == "None":
            return 0
        price = (
            price.replace("руб.", "")
            .replace(" ", "")
            .replace(",", ".")
            .strip()
        )
        return float(price)

    def __parse_coordinates(self, address: str):
        import re

        pattern = r"\(([-+]?[0-9]*\.?[0-9]+), ([-+]?[0-9]*\.?[0-9]+)\)"

        matched = re.search(pattern, address)
        if not matched:
            return None, None
        latitude, longitude = float(matched.group(1)), float(matched.group(2))
        return latitude, longitude

    def before_import_row(self, row, row_number=None, **kwargs):

        phone_number = str(row.get("Рабочий телефон"))
        phone_number = self.__parse_number(phone_number)

        row["Рабочий телефон"] = phone_number

        row["monthly_volume"] = row.get("Ежемесячный объём")

        city = self.__get_city(row)

        row["city"] = city.pk if city else None

        row["price"] = (
                str(row.get("Стоимость продукции в рублях за КГ с НДС")) or "0"
        )
        row["price"] = self.__parse_price(row["price"])

        row["address"] = row.get("Адрес Компании", "")
        address = row.get("address")
        if address and address != "None":
            row["latitude"], row["longitude"] = self.__parse_coordinates(
                row["Адрес Компании"]
            )

    def __get_city(self, row):
        city_name = row.get("Город")
        if city_name:
            if City.objects.filter(name__iexact=city_name).exists():
                return City.objects.filter(name__iexact=city_name).first()
            return City.objects.create(name=city_name)

    def after_import_row(self, row, row_result, row_number=None, **kwargs):
        from django.contrib.auth import get_user_model

        User = get_user_model()

        nds = str(row.get("НДС", "0")) == "1"

        recyclables_name = row.get("Вид сырья")
        if recyclables_name:
            recyclables_subcategory = row.get("Подкатегория")
            recyclables_category = row.get("Категория")
            recyclables = self.__create_recyclables_and_category(
                recyclables_category=recyclables_category,
                recyclables_name=recyclables_name,
                recyclables_subcategory=recyclables_subcategory,
            )

        company = Company.objects.get(
            name=row.get("Название компании"), inn=row.get("inn")
        )

        manager_phone = self.__parse_number(str(row.get("Телефон менеджера")))
        company.manager = User.objects.filter(phone=manager_phone).first()
        company.status = CompanyStatus.VERIFIED
        company.save()
        if recyclables_name:
            application_deal_type = (
                DealType.BUY
                if str(row.get("Покупка")) == "1"
                else DealType.SELL
            )

            CompanyRecyclables.objects.get_or_create(
                company=company,
                recyclables=recyclables,
                monthly_volume=row.get("monthly_volume"),
                price=row.get("price", 0.0),
                action=application_deal_type,
            )

            RecyclablesApplication.objects.get_or_create(
                company=company,
                recyclables=recyclables,
                status=ApplicationStatus.PUBLISHED,
                deal_type=application_deal_type,
                urgency_type=UrgencyType.SUPPLY_CONTRACT,
                price=row["price"],
                volume=row["monthly_volume"],
                with_nds=nds,
                longitude=company.longitude,
                latitude=company.latitude,
                city=company.city,
                address=(company.address or ""),
            )

        advantages = self.__create_advantages(row)
        collection_types = self.__create_recycling_collection(row, row_number)

        for key in advantages.keys():
            activity_type, created = CompanyActivityType.objects.get_or_create(
                company=company, activity=key
            )
            activity_type.rec_col_types.set(collection_types[key])
            activity_type.advantages.set(advantages[key])
            activity_type.save()

    def __create_recyclables_and_category(
            self, recyclables_category, recyclables_name, recyclables_subcategory
    ):
        parent_category, created = RecyclablesCategory.objects.get_or_create(
            name=recyclables_category, defaults={"name": recyclables_category}
        )
        subcategory, created = RecyclablesCategory.objects.get_or_create(
            name=recyclables_subcategory,
            parent=parent_category,
            defaults={
                "name": recyclables_subcategory,
                "parent": parent_category,
            },
        )
        recyclables, created = Recyclables.objects.get_or_create(
            name=recyclables_name, category=subcategory
        )
        return recyclables

    def __create_advantages(self, row):
        supplier = (
            row.get("Преимущества_поставщик").split(",")
            if row.get("Преимущества_поставщик")
            else []
        )
        processor = (
            row.get("Преимущества__переработчик").split(",")
            if row.get("Преимущества__переработчик")
            else []
        )
        buyer = (
            row.get("Преимущества_покупатель").split(",")
            if row.get("Преимущества_покупатель")
            else []
        )
        adv = {
            ActivityType.SUPPLIER: [
                CompanyAdvantage.objects.get_or_create(
                    name=name, activity=ActivityType.SUPPLIER
                )[0]
                for name in supplier
            ],
            ActivityType.PROCESSOR: [
                CompanyAdvantage.objects.get_or_create(
                    name=name, activity=ActivityType.PROCESSOR
                )[0]
                for name in processor
            ],
            ActivityType.BUYER: [
                CompanyAdvantage.objects.get_or_create(
                    name=name, activity=ActivityType.BUYER
                )[0]
                for name in buyer
            ],
        }

        return adv

    def __create_recycling_collection(self, row, row_number=None):
        supplier = (
            row.get("Тип сбора/переработки_поставщик").split(",")
            if row.get("Тип сбора/переработки_поставщик")
            else []
        )
        processor = (
            row.get("Тип сбора/переработки_переработчик").split(",")
            if row.get("Тип сбора/переработки_переработчик")
            else []
        )
        buyer = (
            row.get("Тип сбора/переработки_покупатель").split(",")
            if row.get("Тип сбора/переработки_покупатель")
            else []
        )
        recycling_collection = {
            ActivityType.SUPPLIER: [
                RecyclingCollectionType.objects.get_or_create(
                    name=name, activity=ActivityType.SUPPLIER
                )[0]
                for name in supplier
            ],
            ActivityType.PROCESSOR: [
                RecyclingCollectionType.objects.get_or_create(
                    name=name, activity=ActivityType.PROCESSOR
                )[0]
                for name in processor
            ],
            ActivityType.BUYER: [
                RecyclingCollectionType.objects.get_or_create(
                    name=name, activity=ActivityType.BUYER
                )[0]
                for name in buyer
            ],
        }

        return recycling_collection


class AssignManagerForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    User = get_user_model()
    manager = forms.ModelChoiceField(
        queryset=User.objects.filter(role=3),
        widget=forms.Select,
        required=True,
    )


@admin.register(Company)
class CompanyAdmin(ImportExportModelAdmin, BaseModelAdmin):
    list_display = (
        "id",
        "name",
        "inn",
        "phone",
        "city",
        "address",
        "status",
    )
    search_fields = ("name", "inn")
    list_select_related = ("owner", "manager")
    autocomplete_fields = ("owner", "manager")
    list_filter = ("status",)
    readonly_fields = ("latitude", "longitude")
    inlines = (
        CompanyDocumentInline,
        CompanyRecyclablesInline,
        CompanyAdditionalContactInline,
        CompanyVerificationRequestInline,
        CompanyActivityTypeInline,
    )

    resource_classes = [CompanyResource]
    actions = ["assign_managers"]

    def assign_managers(self, request, queryset):
        form = None
        if "apply" in request.POST:
            form = AssignManagerForm(request.POST)
            if form.is_valid():
                manager = form.cleaned_data["manager"]
                queryset.update(manager=manager)
                # Set the managers for each selected company
                self.message_user(request, "Менеджер успешно назначен")

                return HttpResponseRedirect(request.get_full_path())
        if not form:
            form = AssignManagerForm(
                initial={
                    "_selected_action": queryset.values_list("pk", flat=True)
                }
            )
        return render(
            request,
            "admin/assign_managers.html",
            {
                "companies": queryset,
                "form": form,
                "title": "Назначить менеджера",
            },
        )

    assign_managers.short_description = (
        "Назначить менеджера на выбранные компании"
    )


class CompanyFilter(AutocompleteFilter):
    title = "Компания"
    field_name = "company"


@admin.register(CompanyVerificationRequest)
class CompanyVerificationRequestAdmin(BaseModelAdmin):
    list_display = ("id", "company", "employee", "status", "comment")
    list_select_related = ("company", "employee")
    autocomplete_fields = ("company", "employee")
    list_filter = ("status", CompanyFilter)
    search_fields = (
        "company__name",
        "company__inn",
        "employee__last_name",
        "employee__first_name",
        "employee__phone",
    )


@admin.register(CompanyRecyclables)
class CompanyRecyclablesAdmin(BaseModelAdmin):
    list_display = ("id", "company", "recyclables", "monthly_volume")
    list_select_related = ("company", "recyclables")


class NameActivityAdmin(BaseModelAdmin):
    list_display = ("id", "activity_name", "name")
    list_filter = ("activity",)

    def activity_name(self, obj):
        return ActivityType(obj.activity).label

    activity_name.short_description = "Вид деятельности"


@admin.register(RecyclingCollectionType)
class RecyclingCollectionTypeAdmin(NameActivityAdmin):
    pass


@admin.register(CompanyAdvantage)
class CompanyAdvantageAdmin(NameActivityAdmin):
    pass


@admin.register(City)
class CityAdmin(BaseModelAdmin):
    pass


@admin.register(Region)
class RegionAdmin(BaseModelAdmin):
    pass


@admin.register(District)
class DistrictAdmin(BaseModelAdmin):
    pass


@admin.register(Subscribe)
class SubscribeAdmin(BaseModelAdmin):
    pass


@admin.register(Proposal)
class ProposalAdmin(BaseModelAdmin):
    pass


@admin.register(SpecialApplication)
class SpecialApplicationsAdmin(BaseModelAdmin):
    pass
