from typing import Union

from django.db.models import (
    IntegerChoices,
    TextChoices,
    CharField,
    PositiveSmallIntegerField,
    DecimalField,
)
from django.core.validators import MaxValueValidator, MinValueValidator


def get_field_from_choices(
    label, choices_class, **kwargs
) -> Union[PositiveSmallIntegerField, CharField]:
    """Get django model field from choices class"""

    if issubclass(choices_class, IntegerChoices):
        return PositiveSmallIntegerField(
            label, choices=choices_class.choices, **kwargs
        )
    elif issubclass(choices_class, TextChoices):
        if "max_length" in kwargs:
            max_length = kwargs.pop("max_length")
        else:
            max_length = max([len(v) for v in choices_class.values])

        return CharField(
            label,
            choices=choices_class.choices,
            max_length=max_length,
            **kwargs,
        )
    else:
        raise AssertionError(
            "Unexpected choice class. Must be of IntegerChoices or TextChoices"
        )


class LatitudeField(DecimalField):
    """
    Override for set base max_digits, decimal_places and default values for coordinates
    """

    def __init__(
        self,
        verbose_name="Широта",
        name=None,
        max_digits=18,
        decimal_places=15,
        **kwargs,
    ):
        kwargs["validators"] = [
            MinValueValidator(-90),
            MaxValueValidator(90),
        ]
        super().__init__(
            verbose_name,
            name,
            max_digits,
            decimal_places,
            **kwargs,
        )


class LongitudeField(DecimalField):
    """
    Override for set base max_digits, decimal_places and default values for coordinates
    """

    def __init__(
        self,
        verbose_name="Долгота",
        name=None,
        max_digits=18,
        decimal_places=15,
        **kwargs,
    ):
        kwargs["validators"] = [
            MinValueValidator(-180),
            MaxValueValidator(180),
        ]
        super().__init__(
            verbose_name, name, max_digits, decimal_places, **kwargs
        )


class AmountField(DecimalField):
    """
    Override for set base max_digits, decimal_places and default values
    """

    def __init__(
        self,
        verbose_name=None,
        name=None,
        max_digits=10,
        decimal_places=2,
        **kwargs,
    ):
        if "default" not in kwargs:
            kwargs["default"] = 0.00
        super().__init__(
            verbose_name, name, max_digits, decimal_places, **kwargs
        )
