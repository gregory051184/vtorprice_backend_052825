from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers, exceptions
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.generics import get_object_or_404

from chat.api.serializers import ChatSerializer
from chat.models import Chat
from common.serializers import (
    NonNullDynamicFieldsModelSerializer,
    DynamicFieldsModelSerializer,
    BaseCreateSerializer,
    ContentTypeMixin,
)
from common.utils import generate_random_sequence
from company.api.serializers import CompanySerializer, CreateMyCompanyMixin, CompanyForProposalAndSubscribeSerializer
from company.models import Company, City
from exchange.models import (
    RecyclablesApplication,
    UrgencyType,
    ImageModel,
    RecyclablesDeal,
    DocumentModel,
    DealStatus,
    Review,
    EquipmentApplication,
    EquipmentDeal,
    DealType, SpecialApplication, SpecialApps,
)
from exchange.utils import get_recyclables_application_total_weight
from logistics.models import TransportApplication
from product.api.serializers import (
    RecyclablesSerializer,
    EquipmentSerializer,
    # RecyclingCodeSerializer,
)
from product.models import Recyclables
from user.api.serializers import UserSerializer
from user.models import UserRole


class ImageModelSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = ImageModel


class CreateImageModelSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = ImageModel
        fields = ("image",)


class DocumentSerializer(NonNullDynamicFieldsModelSerializer):
    company = CompanySerializer()

    class Meta:
        model = DocumentModel


class CreateDocumentModelSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = DocumentModel
        fields = ("document", "name", "document_type")


# Сериалайзеры для облегчения запроса на все объявления

class CityForAllRecyclablesApplicationsSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = City
        fields = ("id", "latitude", "longitude", "name")


class CompanyForAllRecyclablesApplicationsSerializer(NonNullDynamicFieldsModelSerializer):
    city = CityForAllRecyclablesApplicationsSerializer()
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    class Meta:
        model = Company
        fields = ("id", "name", "inn", "city", "is_favorite")


class RecyclableCategoryForAllRecyclablesApplicationsSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Recyclables
        fields = ("id", "name")


class RecyclableForAllRecyclablesApplicationsSerializer(NonNullDynamicFieldsModelSerializer):
    category = RecyclableCategoryForAllRecyclablesApplicationsSerializer()

    class Meta:
        model = Recyclables
        fields = ("id", "name", "category")


class AllRecyclablesApplicationsSerializer(NonNullDynamicFieldsModelSerializer):
    company = CompanyForAllRecyclablesApplicationsSerializer()
    recyclables = RecyclableForAllRecyclablesApplicationsSerializer()
    full_weigth = serializers.FloatField()
    total_weight = serializers.FloatField()
    total_price = serializers.DecimalField(max_digits=50, decimal_places=3)
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    class Meta:
        model = RecyclablesApplication
        fields = (
            "id", "deal_type", "urgency_type", "total_weight", "total_price", "created_at", "price", "company",
            "recyclables", "is_deleted", "status", "full_weigth", "is_favorite", "with_nds",
            "application_recyclable_status", "volume", "address")


# _____________________________________________________________________________

class RecyclablesApplicationSerializer(NonNullDynamicFieldsModelSerializer):
    company = CompanySerializer(
        fields=("id", "name", "image", "average_review_rate", "status", "with_nds", "activity_types", "city",
                "monthly_volume", "deals_count", "created_at", "is_favorite", "application_recyclable_status"),
    )
    recyclables = RecyclablesSerializer()
    full_weigth = serializers.FloatField()
    total_weight = serializers.FloatField()
    total_price = serializers.DecimalField(max_digits=50, decimal_places=3)
    nds_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    images = ImageModelSerializer(fields=("id", "image"), many=True)
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )

    class Meta:
        model = RecyclablesApplication


class ApplicationOffersSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = RecyclablesApplication


class UpdateRecyclablesApplicationSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = RecyclablesApplication
        extra_kwargs = {"company": {"required": False}}

    def to_representation(self, instance):
        total_weight = get_recyclables_application_total_weight(instance)
        setattr(instance, "total_weight", total_weight)
        return RecyclablesApplicationSerializer(instance).data

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        company = internal.get("company")
        if not company:
            return internal

        if "city" not in internal:
            internal["city"] = company.city

        if "address" not in internal:
            internal["address"] = company.address
            internal["latitude"] = company.latitude
            internal["longitude"] = company.longitude

        return internal

    def validate(self, attrs):
        user = self.context["request"].user

        company = attrs.get("company")
        if (
                user.role
                not in (
                UserRole.MANAGER,
                UserRole.ADMIN,
                UserRole.SUPER_ADMIN,
        )
                and user.company != company
        ):
            raise exceptions.PermissionDenied

        urgency_type = attrs.get("urgency_type")

        if urgency_type:
            required_fields = []
            required_msg = "Обязательное поле."

            if urgency_type == UrgencyType.READY_FOR_SHIPMENT:
                required = [
                    "lot_size",
                    "is_packing_deduction",
                ]
            elif urgency_type == UrgencyType.SUPPLY_CONTRACT:
                required = ["volume"]
            else:
                required = []

            for field in required:
                if attrs.get(field) is None:
                    required_fields.append(field)

            if required_fields:
                raise serializers.ValidationError(
                    {field: required_msg for field in required_fields}
                )

        if urgency_type == UrgencyType.READY_FOR_SHIPMENT:
            bale_count, bale_weight = attrs.get("bale_count"), attrs.get(
                "bale_weight"
            )
            if not bale_weight:
                total_weight = attrs.get("full_weigth")
            else:
                total_weight = bale_weight * bale_count
            if total_weight > settings.READY_FOR_SHIPMENT_MAX_TOTAL_WEIGHT:
                raise serializers.ValidationError(
                    f"Объем больше {settings.READY_FOR_SHIPMENT_MAX_TOTAL_WEIGHT} кг можно выставить в заявке “Контракт на поставку”, измените срочность заявки"
                )

        return attrs


class CreateRecyclablesApplicationSerializer(
    CreateMyCompanyMixin, UpdateRecyclablesApplicationSerializer
):
    class Meta:
        model = RecyclablesApplication
        extra_kwargs = {"company": {"required": False}}


class CreateEquipmentApplicationSerializer(
    CreateMyCompanyMixin, BaseCreateSerializer
):
    class Meta:
        model = EquipmentApplication
        extra_kwargs = {"company": {"required": False}}

    def to_representation(self, instance):
        return EquipmentApplicationSerializer().to_representation(instance)

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        if "city" not in internal:
            company = internal["company"]
            internal["city"] = company.city
            internal["address"] = company.address
            internal["latitude"] = company.latitude
            internal["longitude"] = company.longitude
        return internal


class EquipmentApplicationSerializer(NonNullDynamicFieldsModelSerializer):
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


class ExchangeRecyclablesSerializer(NonNullDynamicFieldsModelSerializer):
    application_recyclable_status = serializers.IntegerField(read_only=True)
    sales_applications_count = serializers.IntegerField(read_only=True)
    purchase_applications_count = serializers.IntegerField(read_only=True)
    published_date = serializers.DateTimeField(read_only=True)
    lot_size = serializers.FloatField(read_only=True)
    latest_deal_price = serializers.SerializerMethodField(read_only=True)
    deviation_percent = serializers.SerializerMethodField(read_only=True)
    deviation = serializers.SerializerMethodField(read_only=True)

    # recycling_code = RecyclingCodeSerializer(exclude=("recyclables",))

    class Meta:
        model = Recyclables

    def get_latest_deal_price(self, instance: Recyclables):
        # FIXME: Попробовать сделать через аннотации в get_queryset
        try:
            latest_deal = RecyclablesDeal.objects.filter(
                application__recyclables=instance,
                status=DealStatus.COMPLETED,
            ).latest("created_at")
        except RecyclablesDeal.DoesNotExist:
            latest_deal = None
        return latest_deal.price if latest_deal else None

    def get_deviation_percent(self, instance: Recyclables):
        # FIXME: Попробовать сделать через аннотации в get_queryset
        try:
            latest_deal = RecyclablesDeal.objects.filter(
                application__recyclables=instance,
                status=DealStatus.COMPLETED,
            ).latest("created_at")
        except RecyclablesDeal.DoesNotExist:
            latest_deal = None

        if not latest_deal:
            return None

        try:
            pre_latest_deal = (
                RecyclablesDeal.objects.filter(
                    application__recyclables=instance,
                    status=DealStatus.COMPLETED,
                )
                .exclude(pk=latest_deal.pk)
                .latest("created_at")
            )
        except RecyclablesDeal.DoesNotExist:
            pre_latest_deal = None

        if not pre_latest_deal:
            return None

        latest_deal_price = float(latest_deal.price)
        pre_latest_deal_price = float(pre_latest_deal.price)
        return round(
            (latest_deal_price - pre_latest_deal_price)
            / pre_latest_deal_price
            * 100,
            2,
        )

    def get_deviation(self, instance: Recyclables):
        deviation_percent = self.get_deviation_percent(instance)
        if not deviation_percent or deviation_percent == 0:
            return 0
        if deviation_percent > 0:
            return 1
        return -1


class DealReviewSerializer(NonNullDynamicFieldsModelSerializer):
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ("rate", "created_at", "comment", "created_by")

    def get_created_by(self, instance):
        context = self.context
        context["pop_company_review"] = True
        return UserSerializer(
            instance.created_by,
            fields=("id", "first_name", "last_name", "middle_name", "company"),
            context=context,
        ).data


class NeedReviewSerializerMixin(serializers.Serializer):
    """
    Миксин реализующий метод для получения поля, по которому определяется
    выводить окно с запросом оценки по завершению сделки или нет
    """

    need_review = serializers.SerializerMethodField()

    def get_need_review(self, obj):
        # FIXME: в контексте нет реквеста. Ломается все в common/views.py:DocumentsMixin.add_documents()
        if not self.context.get("request"):
            return False

        user = self.context["request"].user
        if (
                not user.is_anonymous
                and user.company_id
                in (obj.supplier_company_id, obj.buyer_company_id)
                and obj.status == DealStatus.COMPLETED
        ):
            company_id = (
                obj.supplier_company_id
                if obj.supplier_company_id != user.company_id
                else obj.buyer_company_id
            )
            if not Review.objects.filter(
                    object_id=obj.id,
                    company_id=company_id,
                    content_type=ContentType.objects.get_for_model(
                        self.Meta.model
                    ),
            ).exists():
                return True
        return False


class RecyclablesDealSerializer(
    NeedReviewSerializerMixin,
    NonNullDynamicFieldsModelSerializer,
    ContentTypeMixin,
):
    supplier_company = CompanySerializer(
        fields=(
            "id",
            "name",
            "phone",
            "city",
            "address",
            "latitude",
            "longitude",
            "image",
        )
    )
    buyer_company = CompanySerializer(
        fields=(
            "id",
            "name",
            "phone",
            "city",
            "address",
            "latitude",
            "longitude",
            "image",
        )
    )
    application = RecyclablesApplicationSerializer(
        exclude=("total_weight", "total_price", "nds_amount")
    )
    total_price = serializers.DecimalField(max_digits=50, decimal_places=3)
    documents = DocumentSerializer(
        fields=(
            "id",
            "document",
            "name",
            "company",
            "document_type",
            "created_at",
        ),
        many=True,
    )
    reviews = DealReviewSerializer(many=True)

    transport_application = serializers.SerializerMethodField()
    # Переопределяем поле, т.к оно по какой-то причине не подхватывается из миксина
    content_type = serializers.SerializerMethodField()

    class Meta:
        model = RecyclablesDeal

    def get_transport_application(self, instance: RecyclablesDeal):
        from logistics.api.serializers import TransportApplicationSerializer

        try:
            application = TransportApplication.objects.get(
                content_type=ContentType.objects.get_for_model(instance),
                object_id=instance.id,
            )
            return TransportApplicationSerializer(
                context=self.context
            ).to_representation(application)
        except TransportApplication.DoesNotExist:
            return None


class RecyclablesDealsForOffers(
    CompanySerializer
):
    class Meta:
        model = Company


class UpdateRecyclablesDealSerializerUsingTransportApplication(
    DynamicFieldsModelSerializer
):
    class Meta:
        model = RecyclablesDeal
        fields = (
            "shipping_date",
            "loaded_weight",
            "delivery_date",
            "accepted_weight",
            "shipping_address",
            "delivery_address",
        )

    def to_representation(self, instance):
        return RecyclablesDealSerializer().to_representation(instance)


class CreateRecyclablesDealSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = RecyclablesDeal
        exclude = ("chat", "deal_number")

    def create(self, validated_data):
        deal_number = generate_random_sequence()
        validated_data["deal_number"] = deal_number
        validated_data["chat"] = Chat.objects.create(
            name=f"Сделка по вторсырью № {deal_number}"
        )
        return super().create(validated_data)

    def to_representation(self, instance):
        return RecyclablesDealSerializer(instance).data


class UpdateRecyclablesDealSerializer(CreateRecyclablesDealSerializer):
    class Meta:
        extra_kwargs = {
            "supplier_company": {"required": False},
            "buyer_company": {"required": False},
            "application": {"required": False},
        }
        model = RecyclablesDeal
        exclude = ("chat",)


class CreateReviewSerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Review
        fields = ("rate", "comment")

    def validate(self, attrs):
        content_type = attrs["content_type"]
        deal = attrs["content_object"]
        company = attrs["company"]
        user = self.context["request"].user

        if user.company not in (deal.supplier_company, deal.buyer_company):
            raise PermissionDenied(
                "Оценить сделку может только участник сделки"
            )

        if Review.objects.filter(
                object_id=deal.id, company=company, content_type=content_type
        ).exists():
            raise ValidationError("Отзыв на эту сделку уже существует")

        return super().validate(attrs)

    def get_parent_model(self):
        requested_url = self.context["request"].stream.path
        if "recyclables_deals" in requested_url:
            return RecyclablesDeal
        elif "equipment_deals" in requested_url:
            return EquipmentDeal
        else:
            raise NotImplementedError("Некорректный тип сделки")

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)

        DealModel = self.get_parent_model()

        content_type = ContentType.objects.get_for_model(DealModel)
        deal = DealModel.objects.select_related(
            "buyer_company", "supplier_company"
        ).get(pk=self.context["view"].kwargs["object_pk"])

        user = self.context["request"].user
        internal["content_type"] = content_type
        internal["content_object"] = deal
        internal["created_by"] = user
        internal["company"] = (
            deal.supplier_company
            if deal.buyer_company == user.company
            else deal.buyer_company
        )

        return internal


class EquipmentDealSerializer(
    NeedReviewSerializerMixin, NonNullDynamicFieldsModelSerializer
):
    supplier_company = CompanySerializer(
        fields=(
            "id",
            "name",
            "phone",
            "city",
            "address",
            "latitude",
            "longitude",
            "image",
        )
    )
    buyer_company = CompanySerializer(
        fields=(
            "id",
            "name",
            "phone",
            "city",
            "address",
            "latitude",
            "longitude",
            "image",
        )
    )
    application = EquipmentApplicationSerializer(exclude=("nds_amount",))
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    transport_application = serializers.SerializerMethodField()
    documents = DocumentSerializer(
        fields=(
            "id",
            "document",
            "name",
            "company",
            "document_type",
            "created_at",
        ),
        many=True,
    )
    reviews = DealReviewSerializer(many=True)

    class Meta:
        model = EquipmentDeal

    def get_transport_application(self, instance: RecyclablesDeal):
        from logistics.api.serializers import TransportApplicationSerializer

        try:
            application = TransportApplication.objects.get(
                content_type=ContentType.objects.get_for_model(instance),
                object_id=instance.id,
            )
            return TransportApplicationSerializer(
                context=self.context
            ).to_representation(application)
        except TransportApplication.DoesNotExist:
            return None


class UpdateEquipmentDealSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = EquipmentDeal
        extra_kwargs = {
            "supplier_company": {"required": False},
            "buyer_company": {"required": False},
            "application": {"required": False},
        }
        exclude = ("chat",)

    def to_representation(self, instance):
        return EquipmentDealSerializer(context=self.context).to_representation(
            instance
        )


class CreateEquipmentDealSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = EquipmentDeal
        exclude = ("chat", "deal_number")

    def create(self, validated_data):
        deal_number = generate_random_sequence()
        validated_data["deal_number"] = deal_number
        validated_data["chat"] = Chat.objects.create(
            name=f"Сделка по оборудованию № {deal_number}"
        )
        return super().create(validated_data)

    def to_representation(self, instance):
        return EquipmentDealSerializer(instance).data


class MatchingApplicationSerializer(serializers.Serializer):
    buying_id = serializers.IntegerField(required=True)
    selling_id = serializers.IntegerField(required=True)

    def validate(self, attrs):
        qs = RecyclablesApplication.objects.all()
        buying_application, selling_application = get_object_or_404(
            qs, pk=attrs["buying_id"]
        ), get_object_or_404(qs, pk=attrs["selling_id"])
        self.__validate_matching_applications(
            buying_application, selling_application
        )
        attrs["buying_application"], attrs["selling_application"] = (
            buying_application,
            selling_application,
        )

        return super().validate(attrs)

    def create(self, validated_data):
        deal_number = generate_random_sequence()
        deal_chat = Chat.objects.create(
            name=f"Сделка по вторсырью № {deal_number}"
        )
        selling_application = validated_data["selling_application"]
        buying_application = validated_data["buying_application"]
        return RecyclablesDeal.objects.create(
            supplier_company=selling_application.company,
            buyer_company=buying_application.company,
            application=selling_application,
            deal_number=deal_number,
            chat=deal_chat,
        )

    def __validate_matching_applications(
            self,
            buying_application: RecyclablesApplication,
            selling_application: RecyclablesApplication,
    ):
        if (
                buying_application.deal_type != DealType.BUY
                or selling_application.deal_type != DealType.SELL
        ):
            raise ValidationError(
                "Получены заявки с неожиданным типом сделки. Ожидалась одна заявка на продажу и одна на покупку. Возможно заявки перепутаны местами"
            )
        if buying_application.recyclables != selling_application.recyclables:
            raise ValidationError("Заявки с разным вторсырьем.")

        if buying_application.urgency_type != selling_application.urgency_type:
            raise ValidationError("Заявки с разной срочностью ")


class SpecialSerializer(NonNullDynamicFieldsModelSerializer):
    companies = CompanyForProposalAndSubscribeSerializer(read_only=True, many=True)
    images = ImageModelSerializer(fields=("id", "image"), many=True)

    # chat = ChatSerializer(read_only=True)

    class Meta:
        model = SpecialApplication
        fields = (
            'id', 'description', 'period', 'price', 'created_at', 'with_nds', 'images', 'companies', 'address',
            'latitude',
            'longitude', 'city', 'chat', 'is_deleted')


class SpecialApplicationsSerializer(NonNullDynamicFieldsModelSerializer):
    companies = CompanyForProposalAndSubscribeSerializer(read_only=True, many=True)
    special_application = SpecialSerializer(read_only=True)

    class Meta:
        model = SpecialApps
        fields = (
            'id', 'payment_number', 'payment_access', 'time_begin', 'time_end', 'companies', 'special_application')
