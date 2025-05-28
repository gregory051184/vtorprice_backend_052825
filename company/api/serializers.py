from django.db import models
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from common.serializers import (
    NonNullDynamicFieldsModelSerializer,
    BaseCreateSerializer,
    LazyRefSerializer,
    BulkCreateListSerializer,
)
from company.models import (
    Company,
    CompanyDocument,
    CompanyRecyclables,
    CompanyAdditionalContact,
    CompanyVerificationRequest,
    RecyclingCollectionType,
    CompanyAdvantage,
    CompanyActivityType,
    City,
    ActivityType,
    CompanyRecyclablesActionType,
    CompanyStatus,
    Region, Proposal,
    Subscribe, SubscribesCompanies, EquipmentProposal, District
)
from exchange.models import (
    ApplicationStatus,
    DealType,
    RecyclablesApplication,
    UrgencyType, ImageModel, EquipmentApplication, DealStatus,
)
from product.api.serializers import RecyclablesSerializer, EquipmentSerializer, RecyclablesShortSerializerForMainFilter
from user.models import UserRole


class CreateMyCompanyMixin:
    # возвращает компанию или название связанную с пользователем из запроса
    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        user = self.context["request"].user
        # getattr(user, "company", None) эквивалент user.company
        # Если нет company в internal а у пользователя в запросе есть company,
        # то internal["company"] = user.company
        if not internal.get("company") and getattr(user, "company", None):
            internal["company"] = user.company
            return internal

        if "company" not in internal:
            if (
                    user.role != UserRole.COMPANY_ADMIN
                    or getattr(user, "my_company", None) is None
            ):
                raise PermissionDenied
            internal["company"] = self.context["request"].user.my_company
        return internal


class DistrictSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = District


class RegionSerializer(NonNullDynamicFieldsModelSerializer):
    # district = DistrictSerializer()

    class Meta:
        model = Region


class CitySerializer(NonNullDynamicFieldsModelSerializer):
    region = RegionSerializer()

    class Meta:
        model = City


class CompanyDocumentSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = CompanyDocument


class CompanySettingsMixin:
    # Проверяет, относится ли пользователь к данной компании
    def check_access(self, attrs):
        user = self.context["request"].user
        attrs = super().validate(attrs)
        company = attrs.get("company")
        company = company or user.company
        if (
                (user.role == UserRole.COMPANY_ADMIN and user.company != company)
                or (user.role == UserRole.MANAGER and company.manager != user)
                or user.role == UserRole.LOGIST
        ):
            raise PermissionDenied(
                "Вы должны быть в находиться компании или являться ее менеджером"
            )
        return attrs

    def validate(self, attrs):
        return self.check_access(attrs)


class CreateCompanyDocumentSerializer(
    # возвращает компанию или название связанную с пользователем из запроса
    CreateMyCompanyMixin,
    # Проверяет, относится ли пользователь к данной компании
    CompanySettingsMixin,
    # Переопределяет метод create
    BaseCreateSerializer
):
    class Meta:
        model = CompanyDocument
        extra_kwargs = {"company": {"required": False}}

    # Переопределяет метод Serializer и возвращает сериализованные данные
    def to_representation(self, instance):
        return CompanyDocumentSerializer(instance).data


class CompanyRecyclablesSerializer(NonNullDynamicFieldsModelSerializer):
    recyclables = RecyclablesSerializer()

    class Meta:
        model = CompanyRecyclables


# Переопределен для поддержки создания приложений, предназначенных для вторичной переработки
class BulkCreateCompanyRecyclablesSerializer(BulkCreateListSerializer):
    """
    Overridden to support the creation recyclables applications
    """

    # Переопределяет метод create, и создаёт экземпляр заявки (RecyclablesApplication)
    def create(self, validated_data):

        to_create = []

        for item in validated_data:
            company = item["company"]
            if company.status in (
                    CompanyStatus.RELIABLE,
                    CompanyStatus.VERIFIED,
            ):
                status = ApplicationStatus.PUBLISHED
            else:
                status = ApplicationStatus.ON_REVIEW

            action = item["action"]
            if action == CompanyRecyclablesActionType.BUY:
                deal_type = DealType.BUY
            else:
                deal_type = DealType.SELL

            is_exists = RecyclablesApplication.objects.filter(
                company=company,
                deal_type=deal_type,
                volume=item["monthly_volume"],
                price=item["price"],
            ).exists()
            if not is_exists:
                to_create.append(
                    RecyclablesApplication(
                        recyclables=item["recyclables"],
                        company=company,
                        status=status,
                        urgency_type=UrgencyType.SUPPLY_CONTRACT,
                        deal_type=deal_type,
                        volume=item["monthly_volume"],
                        price=item["price"],
                        with_nds=company.with_nds,
                        city_id=company.city_id,
                        address=company.address,
                        latitude=company.latitude,
                        longitude=company.longitude,
                    )
                )

        RecyclablesApplication.objects.bulk_create(to_create)

        return super().create(validated_data)


class CreateCompanyRecyclablesSerializer(
    CompanySettingsMixin, CreateMyCompanyMixin, BaseCreateSerializer
):
    class Meta:
        model = CompanyRecyclables
        extra_kwargs = {"company": {"required": False}}

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        # Set list serializer class for support bulk creation
        setattr(
            self.Meta,
            "list_serializer_class",
            BulkCreateCompanyRecyclablesSerializer,
        )

    def to_representation(self, instance):
        return CompanyRecyclablesSerializer(instance).data

    def create(self, validated_data):
        to_delete_from_company = validated_data["company"]
        self.context["to_delete_from_company"] = to_delete_from_company
        return super().create(validated_data)


class CompanyAdditionalContactSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = CompanyAdditionalContact


class CreateCompanyAdditionalContactSerializer(BaseCreateSerializer):
    class Meta:
        model = CompanyAdditionalContact

    def to_representation(self, instance):
        return CompanyAdditionalContactSerializer(instance).data


class RecyclingCollectionTypeSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = RecyclingCollectionType


class CompanyAdvantageSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = CompanyAdvantage


class CompanyActivityTypeSerializer(NonNullDynamicFieldsModelSerializer):
    rec_col_types = RecyclingCollectionTypeSerializer(many=True)
    advantages = CompanyAdvantageSerializer(many=True)

    class Meta:
        model = CompanyActivityType


class CreateCompanyActivityTypeSerializer(
    CreateMyCompanyMixin, CompanySettingsMixin, BaseCreateSerializer
):
    class Meta:
        model = CompanyActivityType

    def to_representation(self, instance):
        return CompanyActivityTypeSerializer(instance).data

    def create(self, validated_data):
        # Preliminary deletion of existing objects
        company = validated_data["company"]
        company.activity_types.filter(
            activity=validated_data["activity"]
        ).delete()
        return super().create(validated_data)

    def validate(self, data):

        rec_col_types = data.get("rec_col_types", [])

        if rec_col_types:
            not_match_rec_col_types_names = []

            for rec_col_type in data["rec_col_types"]:
                if rec_col_type.activity != data["activity"]:
                    not_match_rec_col_types_names.append(rec_col_type.name)

            if not_match_rec_col_types_names:
                message = (
                        "Выбранные типы сбора/переработки не соответствуют типу деятельности: "
                        + ", ".join(not_match_rec_col_types_names)
                )
                raise serializers.ValidationError({"rec_col_types": message})

        advantages = data.get("advantages", [])

        if advantages:
            not_match_advantages_names = []

            for advantage in data["advantages"]:
                if advantage.activity != data["activity"]:
                    not_match_advantages_names.append(advantage.name)

            if not_match_advantages_names:
                message = (
                        "Выбранные преимущества не соответствуют типу деятельности: "
                        + ", ".join(not_match_advantages_names)
                )
                raise serializers.ValidationError({"advantages": message})

        data = super().check_access(data)
        return data


class NonExistCompanySerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Company
        fields = ("name", "inn", "city", "address", "latitude", "longitude")


class ListCompanySerializer(NonNullDynamicFieldsModelSerializer):
    activities = serializers.SerializerMethodField()
    recyclables_type = serializers.SerializerMethodField()
    recyclables_count = serializers.IntegerField(read_only=True)
    recyclables = CompanyRecyclablesSerializer(many=True)
    application_types = serializers.SerializerMethodField()
    city = CitySerializer()
    reviews_count = serializers.SerializerMethodField(read_only=True)
    deals_count = serializers.SerializerMethodField(read_only=True)
    average_review_rate = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    class Meta:
        model = Company

    def get_activities(self, obj):
        # FIXME: оптимизировать по запросам в БД
        activity_types = obj.activity_types.values_list(
            "activity", flat=True
        ).distinct()
        return [ActivityType(item).label for item in activity_types]

    def get_application_types(self, obj):
        # FIXME: оптимизировать по запросам в БД
        application_types = obj.recyclables.values_list(
            "action", flat=True
        ).distinct()
        return [
            CompanyRecyclablesActionType(item).label
            for item in application_types
        ]

    def get_recyclables_type(self, obj):
        # FIXME: оптимизировать по запросам в БД
        company_recyclables = obj.recyclables.select_related(
            "recyclables"
        ).first()
        if company_recyclables:
            return company_recyclables.recyclables.name
        return None

    def get_recyclables_count(self, obj):
        if obj.recyclables_count > 0:
            return obj.recyclables_count - 1
        return obj.recyclables_count

    def get_reviews_count(self, instance: Company):
        return instance.review_set.count()

    # FIXME: сделать через аннотацию
    def get_deals_count(self, instance: Company):
        return (
                instance.recyclables_sell_deals.count()
                + instance.recyclables_buy_deals.count()
                + instance.equipment_buy_deals.count()
                + instance.equipment_sell_deals.count()
        )

    def get_average_review_rate(self, instance: Company):
        return (
                instance.review_set.aggregate(models.Avg("rate"))["rate__avg"]
                or 0.0
        )


# class CompanyRecyclablesForCompaniesMainFiltersPageSerializer(NonNullDynamicFieldsModelSerializer):
#     recyclables = RecyclablesShortSerializerForMainFilter()
#
#     class Meta:
#         model = CompanyRecyclables
#         exclude = ("created_at", "action", "company")


class CompaniesListForMainFilterSerializer(NonNullDynamicFieldsModelSerializer):
    activities = serializers.SerializerMethodField()
    recyclables_type = serializers.SerializerMethodField()
    recyclables_count = serializers.IntegerField(read_only=True)
    # recyclables = CompanyRecyclablesForCompaniesMainFiltersPageSerializer(many=True)
    application_types = serializers.SerializerMethodField()
    city = CitySerializer()
    reviews_count = serializers.SerializerMethodField(read_only=True)
    deals_count = serializers.SerializerMethodField(read_only=True)
    average_review_rate = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )
    has_ready_for_shipment = serializers.SerializerMethodField()
    has_supply_contracts = serializers.SerializerMethodField()
    company_volume = serializers.SerializerMethodField()
    company_recyclables = serializers.SerializerMethodField()
    has_failed_deals = serializers.SerializerMethodField()

    class Meta:
        model = Company
        exclude = ("bank_name", "correction_account", "bic", "description", "inn", "phone", "email")

    def get_has_supply_contracts(self, obj):
        app = obj.recyclables_applications.filter(Q(urgency_type=UrgencyType.SUPPLY_CONTRACT))
        if len(app) > 0:
            return True
        else:
            return False

    def get_has_ready_for_shipment(self, obj):
        app = obj.recyclables_applications.filter(~Q(urgency_type=UrgencyType.SUPPLY_CONTRACT),
                                                  Q(status__lte=ApplicationStatus.ON_REVIEW), ~Q(is_deleted=1))
        if len(app) > 0:
            return True
        else:
            return False

    def get_company_volume(self, obj):
        return sum(obj.recyclables_sell_deals.values_list("weight", flat=True)) + sum(
            obj.recyclables_buy_deals.values_list("weight", flat=True))

    def get_company_recyclables(self, obj):
        return obj.recyclables_applications.values_list("recyclables", flat=True)

    def get_has_failed_deals(self, obj):
        buy = obj.recyclables_buy_deals.filter(Q(status__lte=DealStatus.COMPLETED))
        sell = obj.recyclables_sell_deals.filter(Q(status__lte=DealStatus.COMPLETED))
        return True if len(buy) > 0 and len(sell) > 0 else False

    def get_activities(self, obj):
        # FIXME: оптимизировать по запросам в БД
        activity_types = obj.activity_types.values_list(
            "activity", flat=True
        ).distinct()
        return [ActivityType(item).label for item in activity_types]

    def get_application_types(self, obj):
        # FIXME: оптимизировать по запросам в БД
        application_types = obj.recyclables.values_list(
            "action", flat=True
        ).distinct()
        return [
            CompanyRecyclablesActionType(item).label
            for item in application_types
        ]

    def get_recyclables_type(self, obj):
        # FIXME: оптимизировать по запросам в БД
        company_recyclables = obj.recyclables.select_related(
            "recyclables"
        ).first()
        if company_recyclables:
            return company_recyclables.recyclables.name
        return None

    def get_recyclables_count(self, obj):
        if obj.recyclables_count > 0:
            return obj.recyclables_count - 1
        return obj.recyclables_count

    def get_reviews_count(self, instance: Company):
        return instance.review_set.count()

    # FIXME: сделать через аннотацию
    def get_deals_count(self, instance: Company):
        return (
                instance.recyclables_sell_deals.count()
                + instance.recyclables_buy_deals.count()
                + instance.equipment_buy_deals.count()
                + instance.equipment_sell_deals.count()
        )

    def get_average_review_rate(self, instance: Company):
        return (
                instance.review_set.aggregate(models.Avg("rate"))["rate__avg"]
                or 0.0
        )


class CompanySerializer(NonNullDynamicFieldsModelSerializer):
    documents = CompanyDocumentSerializer(many=True)
    recyclables = CompanyRecyclablesSerializer(many=True)
    contacts = CompanyAdditionalContactSerializer(many=True)
    activity_types = CompanyActivityTypeSerializer(many=True)
    city = CitySerializer()
    manager = LazyRefSerializer(
        "user.api.serializers.UserSerializer", exclude=("company", "groups")
    )
    owner = LazyRefSerializer(
        "user.api.serializers.UserSerializer", exclude=("company", "groups")
    )
    recyclables_count = serializers.IntegerField(read_only=True)
    monthly_volume = serializers.FloatField(read_only=True)
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )
    reviews_count = serializers.SerializerMethodField(read_only=True)
    deals_count = serializers.SerializerMethodField(read_only=True)
    average_review_rate = serializers.SerializerMethodField(read_only=True)
    reviews = serializers.SerializerMethodField()
    deals_by_recyclable_for_offers = serializers.IntegerField(read_only=True)
    last_deal_date = serializers.CharField(read_only=True)
    buy_apps_by_recyclable_for_offers = serializers.IntegerField(read_only=True)
    last_buy_app_date = serializers.CharField(read_only=True)
    app_offers_count = serializers.IntegerField(read_only=True)
    # ДОБАВИЛ
    with_nds = serializers.BooleanField(
        read_only=True, required=False, default=False
    )
    # ДОБАВИЛ ДЛЯ ОПРЕДЕЛЕНИЯ КОЛ-ВО ЗАЯВОК и ОГРАНИЧЕНИЯ СОЗДАНИЯ
    total_applications_count = serializers.SerializerMethodField()

    def get_total_applications_count(self, obj):
        return obj.recyclables_applications.count()

    def get_reviews(self, instance):
        from exchange.api.serializers import DealReviewSerializer

        return DealReviewSerializer(instance.review_set, many=True).data

    def get_reviews_count(self, instance: Company):
        return instance.review_set.count()

    # FIXME: сделать через аннотацию и добавить кол-во сделок по оборудованию
    def get_deals_count(self, instance: Company):
        return (
                instance.recyclables_sell_deals.count()
                + instance.recyclables_buy_deals.count()
        )

    def get_average_review_rate(self, instance: Company):
        return (
                instance.review_set.aggregate(models.Avg("rate"))["rate__avg"]
                or 0.0
        )

    class Meta:
        model = Company


class SetOwnerCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ()


class CreateCompanySerializer(serializers.ModelSerializer):
    phone = serializers.CharField(max_length=128, required=False)

    class Meta:
        model = Company
        fields = (
            "inn",
            "bic",
            "payment_account",
            "correction_account",
            "bank_name",
            "name",
            "head_full_name",
            "description",
            "address",
            "email",
            "phone",
            "city",
            "latitude",
            "longitude",
            "image",
            "with_nds",

            "staff",
            "suspend_staff",
        )

    def to_representation(self, instance):
        return CompanySerializer(instance).data

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["owner"] = user
        if "phone" not in validated_data:
            validated_data["phone"] = user.phone
        region_name = validated_data["address"].split(',')[1]
        # Для создания региона
        current_region = Region.objects.get_or_create(name=region_name)
        instance = super().create(validated_data)
        # Для привязки города к региону
        if not instance.city.region:
            city = City.objects.get(id=instance.city.id)
            city.region = current_region[0]
            city.save()
        # Set company for owner
        user.company = instance
        user.save()

        return instance


class CompanyVerificationRequestSerializer(
    NonNullDynamicFieldsModelSerializer
):
    company = CompanySerializer(exclude=("manager", "owner"))
    employee = LazyRefSerializer(
        "user.api.serializers.UserSerializer", exclude=("company",)
    )

    class Meta:
        model = CompanyVerificationRequest


class CreateCompanyVerificationRequestSerializer(
    CreateMyCompanyMixin, CompanySettingsMixin, serializers.ModelSerializer
):
    class Meta:
        model = CompanyVerificationRequest
        fields = ()

    def validate(self, attrs):
        company = attrs["company"]
        if company.status in (CompanyStatus.VERIFIED, CompanyStatus.RELIABLE):
            raise serializers.ValidationError("Компания уже верифицирована")
        return attrs

    def to_representation(self, instance):
        return CompanyVerificationRequestSerializer(instance).data


class UpdateCompanyVerificationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyVerificationRequest
        fields = ("status", "comment")

    def to_representation(self, instance):
        return CompanyVerificationRequestSerializer(instance).data


# Добавил этот сериалайзер, чтобы избежать цикличность с RecyclablesApplicationSerializer

class ImageModelSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = ImageModel


class RecyclablesApplicationForProposalSerializer(NonNullDynamicFieldsModelSerializer):
    company = CompanySerializer(
        fields=("id", "name", "image", "average_review_rate", "status", "with_nds", "activity_types", "city",
                "created_at", "is_favorite")
    )
    recyclables = RecyclablesSerializer()
    full_weigth = serializers.FloatField()
    total_price = serializers.DecimalField(max_digits=50, decimal_places=3)
    nds_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    images = ImageModelSerializer(fields=("id", "image"), many=True)

    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    class Meta:
        model = RecyclablesApplication


class CompanyForProposalAndSubscribeSerializer(NonNullDynamicFieldsModelSerializer):
    recyclables = CompanyRecyclablesSerializer(many=True)
    contacts = CompanyAdditionalContactSerializer(many=True)
    activity_types = CompanyActivityTypeSerializer(many=True)
    city = CitySerializer()
    recyclables_count = serializers.IntegerField(read_only=True)
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )
    average_review_rate = serializers.SerializerMethodField(read_only=True)
    deals_by_recyclable_for_offers = serializers.IntegerField(read_only=True)
    # ДОБАВИЛ
    with_nds = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    def get_average_review_rate(self, instance: Company):
        return (
                instance.review_set.aggregate(models.Avg("rate"))["rate__avg"]
                or 0.0
        )

    class Meta:
        model = Company


class EquipmentApplicationForProposalSerializer(NonNullDynamicFieldsModelSerializer):
    company = CompanySerializer(
        fields=("id", "name", "image", "average_review_rate", "status")
    )
    equipment = EquipmentSerializer()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    nds_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    images = ImageModelSerializer(fields=("id", "image"), many=True)

    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    class Meta:
        model = EquipmentApplication


# _____________________________________________________________________________________________________

class ProposalSerializer(NonNullDynamicFieldsModelSerializer):
    companies = CompanyForProposalAndSubscribeSerializer(read_only=True, many=True)
    applications = RecyclablesApplicationForProposalSerializer(read_only=True, many=True)

    class Meta:
        model = Proposal
        fields = ('id', 'sender_company', 'companies', 'applications', 'created_at', 'special_id')


class EquipmentProposalSerializer(NonNullDynamicFieldsModelSerializer):
    companies = CompanyForProposalAndSubscribeSerializer(read_only=True, many=True)
    applications = EquipmentApplicationForProposalSerializer(read_only=True, many=True)

    class Meta:
        model = EquipmentProposal
        fields = ('id', 'sender_company', 'companies', 'applications', 'created_at', 'special_id')


class SubscribeSerializer(NonNullDynamicFieldsModelSerializer):
    companies = CompanyForProposalAndSubscribeSerializer(read_only=True, many=True)

    class Meta:
        model = Subscribe
        fields = ('id', 'companies', 'name', 'description', 'level', 'period', 'price', 'created_at')


class SubscribeCompanySerializer(NonNullDynamicFieldsModelSerializer):
    companies = CompanyForProposalAndSubscribeSerializer(read_only=True, many=True)
    subscribe = SubscribeSerializer(read_only=True)

    class Meta:
        model = SubscribesCompanies
        fields = (
            'id', 'payment_number', 'payment_access', 'time_begin', 'time_end', 'companies', 'subscribe', 'is_deleted',
            'company')
