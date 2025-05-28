from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import Group
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from common.serializers import (
    NonNullDynamicFieldsModelSerializer,
    BaseCreateSerializer,
    LazyRefSerializer,
)
from user.models import UserRole
from user.utils import get_all_permissions

User = get_user_model()


class CreateUserSerializer(BaseCreateSerializer):
    id = serializers.ReadOnlyField()
    is_created = serializers.BooleanField(default=False, read_only=True)

    class Meta:
        model = User
        fields = ("id", "phone", "is_created")


class GroupSerializer(NonNullDynamicFieldsModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Group

    def get_permissions(self, obj):
        all_permissions = get_all_permissions()
        group_permissions = set(
            [
                p.content_type.app_label + "." + p.codename
                for p in obj.permissions.all()
            ]
        )
        return {p: p in group_permissions for p in all_permissions}


class UserSerializer(NonNullDynamicFieldsModelSerializer):
    company = serializers.SerializerMethodField()
    groups = GroupSerializer(many=True)

    class Meta:
        model = User
        fields = (
            "id",
            "last_name",
            "first_name",
            "middle_name",
            "birth_date",
            "email",
            "phone",
            "company",
            "position",
            "status",
            "role",
            "groups",
            "updated_at",
            "image",
        )

    def get_company(self, obj):
        company = obj.my_company if hasattr(obj, "my_company") else obj.company
        if self.context.get("pop_company_review"):
            exclude_arg = {"exclude": ("reviews",)}
        else:
            exclude_arg = {}
        if company:
            return LazyRefSerializer(
                "company.api.serializers.CompanySerializer",
                company,
                **exclude_arg,
            ).data


class UpdateUserRoleSerializer(BaseCreateSerializer):
    class Meta:
        model = User
        fields = ("role",)

    def to_representation(self, instance):
        return UserSerializer(instance).data

    def update(self, instance, validated_data):
        requested_user = self.context["request"].user
        if requested_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise PermissionDenied
        return super().update(instance, validated_data)


class UpdateUserSerializer(BaseCreateSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "last_name",
            "first_name",
            "middle_name",
            "position",
            "phone",
            "image",
        )

    def to_representation(self, instance):
        return UserSerializer(instance).data


class PhoneConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=4, max_length=4)


class UserObtainTokenSerializer(TokenObtainPairSerializer):
    phone = PhoneNumberField()
    password = serializers.CharField()

    def validate(self, attrs):
        data = {}
        self.user = authenticate(
            **{
                "request": self.context["request"],
                self.username_field: attrs[self.username_field],
                "password": attrs["password"],
            }
        )

        refresh = self.get_token(self.user)

        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        return data
