from rest_framework import serializers

from common.serializers import (
    NonNullDynamicFieldsModelSerializer,
    BaseCreateSerializer,
)
from product.models import (
    Recyclables,
    RecyclablesCategory,
    EquipmentCategory,
    Equipment,
)


class ShortRecyclablesCategorySerializer(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = RecyclablesCategory


class ShortEquipmentCategorySerializer(ShortRecyclablesCategorySerializer):
    class Meta:
        model = EquipmentCategory


class RecyclablesSerializer(NonNullDynamicFieldsModelSerializer):
    category = ShortRecyclablesCategorySerializer()

    class Meta:
        model = Recyclables


class RecyclablesShortSerializerForMainFilter(NonNullDynamicFieldsModelSerializer):
    class Meta:
        model = Recyclables
        fields = ("id",)


class CreateRecyclablesSerializer(BaseCreateSerializer):
    class Meta:
        model = Recyclables

    def to_representation(self, instance):
        return RecyclablesSerializer(instance).data


class RecursiveField(serializers.Serializer):
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class RecyclablesCategorySerializer(NonNullDynamicFieldsModelSerializer):
    subcategories = RecursiveField(many=True)
    recyclables = RecyclablesSerializer(many=True, exclude=("category",))

    class Meta:
        model = RecyclablesCategory


class EquipmentCategorySerializer(NonNullDynamicFieldsModelSerializer):
    subcategories = RecursiveField(many=True)
    equipments = RecyclablesSerializer(many=True, exclude=("category",))

    class Meta:
        model = EquipmentCategory


class EquipmentSerializer(NonNullDynamicFieldsModelSerializer):
    category = ShortEquipmentCategorySerializer()

    class Meta:
        model = Equipment


class CreateEquipmentSerializer(BaseCreateSerializer):
    class Meta:
        model = Equipment

    def to_representation(self, instance):
        return EquipmentSerializer(instance).data

# TODO: Add later
#
# class RecyclingCodeSerializer(NonNullDynamicFieldsModelSerializer):
#     recyclables = RecyclablesSerializer(many=True, exclude=("recycling_code",))
#
#     class Meta:
#         model = RecyclingCode
