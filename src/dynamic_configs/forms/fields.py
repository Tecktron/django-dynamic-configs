"""Form fields for config values, and ``formfield_for``, which picks the field for a type."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.forms.list import TypedLineListField
from dynamic_configs.types.base import ConfigType, Serializer
from dynamic_configs.types.serializers import (
    DaysSerializer,
    HoursSerializer,
    MinutesSerializer,
    SecondsSerializer,
    WeeksSerializer,
)

_DURATION_SERIALIZERS = {
    "seconds": SecondsSerializer,
    "minutes": MinutesSerializer,
    "hours": HoursSerializer,
    "days": DaysSerializer,
    "weeks": WeeksSerializer,
}


class SerializerField(forms.CharField):
    """A text input cleaned with a serializer's ``deserialize`` and shown with its ``serialize``.

    This is the admin field for custom types that don't name a ``form``.
    """

    def __init__(self, serializer: Serializer, **kwargs: Any) -> None:
        """Use ``serializer`` to read and show the value."""
        self.serializer = serializer
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        """Show a value as its serialized text; leave text (re-displayed input) and None as they are."""
        if value is None or isinstance(value, str):
            return value
        return self.serializer.serialize(value)

    def to_python(self, value: Any) -> Any:
        """Return the value written in the input, or None when it's empty."""
        text = super().to_python(value)
        if text in self.empty_values:
            return None
        try:
            return self.serializer.deserialize(text)
        except ValueError as error:
            raise ValidationError(str(error)) from error


class DurationUnitField(SerializerField):
    """A duration entered as a plain number of one unit (``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``)."""

    def __init__(self, unit: str, **kwargs: Any) -> None:
        """Read and show the duration as a number of ``unit``."""
        self.unit = unit
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal"}))
        super().__init__(_DURATION_SERIALIZERS[unit](), **kwargs)


def formfield_for(config_type: ConfigType, *, allow_null: bool = False, **kwargs: Any) -> forms.Field:
    """Return the form field for editing a value of ``config_type``.

    :param config_type: the config's type
    :param allow_null: whether the config may be empty; a boolean then gets a three-way (yes/no/unknown) field
    :param kwargs: options for the field, such as ``required``, ``label`` and ``help_text``
    :returns: a ``TypedLineListField`` for list and set types, the type's ``form_class``, or a ``SerializerField``
    :rtype: forms.Field
    """
    if config_type.container is not None:
        return TypedLineListField(config_type.item_type, unique=config_type.container == "set", **kwargs)
    form_class = config_type.form_class
    if form_class is None:
        return SerializerField(config_type.serializer, **kwargs)
    if allow_null and form_class is forms.BooleanField:
        # A checkbox can't be empty, so a boolean that allows None needs a yes/no/unknown choice.
        form_class = forms.NullBooleanField
    return form_class(**kwargs)
