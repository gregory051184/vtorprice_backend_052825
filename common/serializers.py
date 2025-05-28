from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers, exceptions
from rest_framework.settings import import_from_string


class ChoiceAsDictField(serializers.ChoiceField):
    """
    Serializes field with choices as a dictionary to provide both value and label of the choice.
    """

    def to_representation(self, value):
        if value in ("", None):
            return None
        return {"id": value, "label": self.choices[value]}


class NonNullModelSerializer(serializers.ModelSerializer):
    """
    Remove null fields from representation
    """

    # Убирает все нулевые поля из представления
    def to_representation(self, instance):
        try:
            result = super().to_representation(instance)
        # This error be raised when invalid parameter of expand passed
        except ValueError:
            raise exceptions.ValidationError
        return OrderedDict(
            [(key, result[key]) for key in result if result[key] is not None]
        )


class BulkCreateListSerializer(serializers.ListSerializer):
    """
    Overridden to support bulk creation of objects with a
    single query to the database through bulk_create method

    source: https://medium.com/swlh/efficient-bulk-create-with-django-rest-framework-f73da6af7ddc
    """

    def create(self, validated_data):
        to_create = [self.child.create(attrs) for attrs in validated_data]

        # Preliminary deletion of existing objects
        # Предварительное удаление существующих объектов
        if self.context.get("with_removal", False):
            if to_delete_from_company := self.context.get(
                    "to_delete_from_company"
            ):
                to_delete_from_company.recyclables.all().delete()
            else:
                self.child.Meta.model.objects.all().delete()

        try:
            self.child.Meta.model.objects.bulk_create(to_create)
        except Exception as e:
            raise exceptions.ValidationError(e)

        return to_create


# Расширяет класс ModelSerializer полями fields and exclude
class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
     A base ModelSerializer used by default in the project. Extends default ModelSerializer by:
    * using additional `fields` or 'exclude' arguments that controls
      which fields should be displayed. If both arguments are passed
      at the same time and the field is in both, it will be excluded

    * allowing the fields to be defined on a per-view/request basis,
      fields can be whitelisted, blacklisted, and child serializers
      can be optionally expanded through SerializerExtensionsMixin

    Source:
    https://www.django-rest-framework.org/api-guide/serializers/#dynamically-modifying-fields
    """

    is_deleted = serializers.BooleanField(read_only=True)

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' and 'exclude' args up to the superclass
        fields = kwargs.pop("fields", None)
        exclude = kwargs.pop("exclude", None)

        # Instantiate the superclass normally
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)

        # Set fields attribute as __all__ if fields and exclude
        # attributes not explicit specified in Meta class
        # Если поля fields и exclude не определены в Meta,
        # тогда серализуются все поля
        if (
                getattr(self.Meta, "fields", None) is None
                and getattr(self.Meta, "exclude", None) is None
        ):
            setattr(self.Meta, "fields", "__all__")

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

        if exclude is not None:
            # Drop fields that are specified in the `exclude` argument.
            for field_name in set(exclude):
                self.fields.pop(field_name)


class NonNullDynamicFieldsModelSerializer(
    DynamicFieldsModelSerializer, NonNullModelSerializer
):
    serializer_choice_field = ChoiceAsDictField


class BaseCreateSerializer(DynamicFieldsModelSerializer):
    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        # Set list serializer class for support bulk creation
        # Если в Meta нет list_serializer_class, тогда используется BulkCreateListSerializer
        setattr(self.Meta, "list_serializer_class", BulkCreateListSerializer)

    def create(self, validated_data):
        """
        Overridden to avoid creation object when bulk creation
        :param validated_data:
        :return: created instance
        """
        fields = self.Meta.model._meta.get_fields()
        m2m_fields = []
        for field in fields:
            if field.many_to_many:
                m2m_fields.append(field)

        set_map = {}
        for m2m in m2m_fields:
            if m2m.name in validated_data:
                set_map[m2m.name] = validated_data.pop(m2m.name)
        # создаётся новый экземпляр
        instance = self.Meta.model(**validated_data)
        if isinstance(self._kwargs["data"], dict):
            instance.save()

            if set_map:
                for field, objects in set_map.items():
                    manager = getattr(instance, field)
                    manager.set(objects)

        return instance


class LazyRefSerializer(serializers.ModelSerializer):
    def __init__(self, ref, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._reference_as_string = ref
        self._reference_as_serializer = None

    def __getattr__(self, item):
        return getattr(self._reference_as_serializer, item)

    def __getattribute__(self, attr):
        # When first trying to use its attributes, it imports and initializes the original serializer
        # The 'not in' check is to avoid infinite loops. _creation_counter is called when initializing the serializer which uses this LazyRefSerializer field
        if (
                attr
                not in [
            "args",
            "kwargs",
            "_reference_as_string",
            "_reference_as_serializer",
            "_creation_counter",
        ]
                and self._reference_as_serializer is None
        ):
            referenced_serializer = import_from_string(
                self._reference_as_string, ""
            )
            self._reference_as_serializer = referenced_serializer(
                *self.args, **self.kwargs
            )
            self.__class__ = referenced_serializer
            self.__dict__.update(self._reference_as_serializer.__dict__)
        return object.__getattribute__(self, attr)


class FavoriteSerializer(metaclass=serializers.SerializerMetaclass):
    # TODO: придумать как без наследования от serializers.Serializer
    # реюзать класс так, чтобы ничего не ломалось
    is_favorite = serializers.BooleanField(
        read_only=True, required=False, default=False
    )


class EmptySerializer(serializers.Serializer):
    pass


class ContentTypeMixin:
    content_type = serializers.SerializerMethodField()

    def get_content_type(self, instance):
        return ContentType.objects.get_for_model(instance).model
