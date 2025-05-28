from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from chat.api.serializers import ChatSerializer
from company.api.serializers import CitySerializer
from exchange.api.serializers import (
    UpdateRecyclablesDealSerializerUsingTransportApplication,
    DocumentSerializer,
)
from exchange.models import DealStatus, RecyclablesDeal, EquipmentDeal
from logistics.models import (
    Contractor,
    ContractorType,
    TransportApplication,
    LogisticsOffer,
    TransportApplicationStatus,
    RECYCLABLE_DEAL_TO_TRANSPORT_APPLICATION_STATUS_MAPPING,
    LogisticOfferStatus,
    LogistTransportApplicationStatus,
)
from common.serializers import (
    DynamicFieldsModelSerializer,
    NonNullDynamicFieldsModelSerializer,
    BaseCreateSerializer,
    ContentTypeMixin,
)
from logistics.signals import transport_application_status_update
from user.api.serializers import UserSerializer
from user.models import UserRole


class ContractorSerializer(NonNullDynamicFieldsModelSerializer):
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Contractor


class CreateContractorSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = Contractor
        exclude = ("created_by",)

    def validate(self, attrs):
        contractor_type = attrs.get("contractor_type")
        required_msg = "Обязательное поле."
        required_fields = []

        if contractor_type == ContractorType.TRANSPORT:
            required = ["transport_owns_count"]

        else:
            required = []
        required.append("address")

        for field in required:
            if attrs.get(field) is None:
                required_fields.append(field)
        if required_fields:
            raise serializers.ValidationError(
                {field: required_msg for field in required_fields}
            )

        return attrs

    def to_representation(self, instance):
        return ContractorSerializer(instance).data


class TransportApplicationSerializer(
    NonNullDynamicFieldsModelSerializer, ContentTypeMixin
):
    shipping_city = CitySerializer()
    delivery_city = CitySerializer()
    logist_status = serializers.ChoiceField(
        allow_null=True,
        default=None,
        choices=LogistTransportApplicationStatus.choices,
    )
    my_offer = serializers.SerializerMethodField()
    deal_type = serializers.SerializerMethodField()

    content_type = serializers.SerializerMethodField()
    approved_logistics_offer = serializers.SerializerMethodField()
    documents = DocumentSerializer(
        fields=("id", "document", "name", "document_type"), many=True
    )

    def get_my_offer(self, instance: TransportApplication):
        if (
                self.context.get("request")
                and not self.context.get("request").user.is_anonymous
                and self.context.get("request").user.role == UserRole.LOGIST
        ):
            my_offer = LogisticsOffer.objects.filter(
                logist=self.context.get("request").user, application=instance
            ).first()
            if my_offer:
                return LogisticsOfferSerializer(
                    my_offer, exclude=("application",)
                ).data
        return None

    class Meta:
        model = TransportApplication

    def get_approved_logistics_offer(self, instance):
        if not self.context.get("request"):
            return None
        user = self.context.get("request").user
        if user.is_anonymous or user.role == UserRole.LOGIST:
            return None
        if not instance.approved_logistics_offer:
            return None
        return LogisticsOfferSerializer(
            instance.approved_logistics_offer, exclude=("application",)
        ).data

    def get_deal_type(self, instance):
        if instance.deal:
            return ContentType.objects.get_for_model(instance.deal).model


class CreateTransportApplicationSerializer(BaseCreateSerializer):
    deal_type = serializers.ChoiceField(
        choices=["recyclables", "equipment"], required=False
    )

    class Meta:
        model = TransportApplication
        exclude = ("created_by", "approved_logistics_offer", "content_type")
        extra_kwargs = {"object_id": {"required": False}}

    def to_representation(self, instance):
        return TransportApplicationSerializer(instance).data

    def validate(self, attrs):
        if ("deal_type" in attrs and "object_id" not in attrs) or (
                "object_id" in attrs and "deal_type" not in attrs
        ):
            required_msg = "Обязательное поле."
            raise serializers.ValidationError(
                {
                    field: required_msg
                    for field in ["deal_type", "object_id"]
                    if field not in attrs
                }
            )
        return super().validate(attrs)

    def create(self, validated_data):
        if "deal_type" in validated_data:
            deal_type = validated_data.pop("deal_type")
            deal_id = validated_data.pop("object_id")
            validated_data["deal"] = self._change_deal_status(
                deal_id, deal_type
            )
        return super().create(validated_data)

    def _change_deal_status(self, deal_id, deal_type):
        # When creating transport application, set Deal status to "DISPATCHER_APPOINTMENT"
        deals_models_map = {
            "recyclables": RecyclablesDeal,
            "equipment": EquipmentDeal,
        }
        deal_model = deals_models_map.get(deal_type)
        if not deal_model:
            raise serializers.ValidationError(
                {"deal_type": "Некорректное значение"}
            )
        deal = get_object_or_404(deal_model, pk=deal_id)
        deal.status = DealStatus.DISPATCHER_APPOINTMENT
        deal.save()
        return deal


class UpdateTransportApplicationSerializer(
    NonNullDynamicFieldsModelSerializer
):
    deal = UpdateRecyclablesDealSerializerUsingTransportApplication(
        fields=(
            "delivery_date",
            "accepted_weight",
            "shipping_date",
            "loaded_weight",
            "shipping_address",
            "delivery_address",
        ),
        required=False,
    )

    class Meta:
        model = TransportApplication
        exclude = ("created_by",)

    def validate(self, attrs):
        deal_attrs, required = attrs.get("deal"), self.get_required_fields(
            attrs.get("status")
        )
        self._validate_deal_attrs(deal_attrs, required)
        return super().validate(attrs)

    def _validate_deal_attrs(self, deal_attrs, required):
        """
        Validating that required deal fields presents
        """
        required_msg = "Обязательное поле."
        required_fields = []
        for field in required:
            if deal_attrs.get(field) is None:
                required_fields.append(field)

        if required_fields:
            raise serializers.ValidationError(
                {field: required_msg for field in required_fields}
            )

    def update(self, instance: TransportApplication, validated_data):
        new_status = validated_data.get("status")
        deal_data = validated_data.pop("deal")
        deal = instance.deal
        # ДОБАВИЛ
        for field in deal_data.keys():
            setattr(instance, field, deal_data[field])
        instance.save()
        # _____________________________________________________
        transport_application_status_update.send_robust(
            TransportApplication, instance=instance, new_status=new_status
        )

        if deal:
            for field in deal_data.keys():
                setattr(deal, field, deal_data[field])

            deal.save()
            self._handle_user_status_change(
                instance, new_status, validated_data
            )

        return super().update(instance, validated_data)

    def get_required_fields(self, status: TransportApplicationStatus):
        if status == TransportApplicationStatus.COMPLETED:
            return ["delivery_date", "accepted_weight"]
        if status == TransportApplicationStatus.UNLOADING:
            return ["shipping_date", "loaded_weight"]

        return []

    def _handle_user_status_change(self, instance, new_status, validated_data):
        if new_status == TransportApplicationStatus.UNLOADING:
            # если транспортная заявка перешла в статус "Машина загружена" - отклоняем все прочие предложения
            approved_offer = instance.approved_logistics_offer
            approved_offer.decline_all_other_offers()

        elif new_status == TransportApplicationStatus.CANCELED:
            # если пользователь решил отменить транспортную заявку, отклоняем все предложения логистов
            instance.offers.get_queryset().update(
                status=LogisticOfferStatus.DECLINED
            )

        deal_new_status = RECYCLABLE_DEAL_TO_TRANSPORT_APPLICATION_STATUS_MAPPING.get(
            validated_data.get(
                "status"
            )  # <- статус заявки по транспорту. Из него маппим статус сделки и ниже его назначаем
        )
        # Назначем статус сделки
        if deal_new_status and instance.deal:
            instance.deal.status = deal_new_status
            instance.deal.save()

    def to_representation(self, instance):
        return TransportApplicationSerializer(
            context=self.context
        ).to_representation(instance)


class CreateLogisticsOfferSerializer(BaseCreateSerializer):
    class Meta:
        model = LogisticsOffer
        exclude = ("status", "name", "chat")
        read_only_fields = ("logist",)

    def to_representation(self, instance):
        return LogisticsOfferSerializer(
            context=self.context
        ).to_representation(instance)

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data[
            "name"
        ] = f'Предложение от логиста {user.last_name} {user.first_name} {validated_data["amount"]} руб. до {validated_data["shipping_date"]}'

        return super().create(validated_data)


class UpdateLogisticsOffer(BaseCreateSerializer):
    def to_representation(self, instance):
        return LogisticsOfferSerializer(
            context=self.context
        ).to_representation(instance)

    class Meta:
        model = LogisticsOffer
        exclude = ("name", "chat")
        read_only_fields = ("logist", "application")

    def update(self, instance: LogisticsOffer, validated_data):
        if validated_data.get("status") == LogisticOfferStatus.APPROVED:
            instance.application.approved_logistics_offer = instance
            instance.application.save()

        return super().update(instance, validated_data)


class LogisticsOfferSerializer(NonNullDynamicFieldsModelSerializer):
    application = TransportApplicationSerializer(read_only=True)
    contractor = ContractorSerializer()
    chat = serializers.SerializerMethodField()
    logist = UserSerializer(exclude=("company", "email", "groups"))

    class Meta:
        model = LogisticsOffer

    def get_chat(self, instance):
        from chat.models import Chat

        chat: Chat = instance.chat
        if (
                self.context
        ):  # FIXME: разобраться почему не передается контекст при создании оффера
            user = self.context["request"].user
            chat.unread_count = chat.messages.filter(
                Q(is_read=False) & ~Q(author=user)
            ).count()
        return ChatSerializer(chat, context=self.context).data
