"""Form fields for config values, and ``formfield_for``, which picks the field for a type."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.conf import get_settings
from dynamic_configs.forms.list import SET_HELP, TypedLineListField
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
_BOOLEAN_HELP = "Checked means true."
_NULL_BOOLEAN_HELP = "Unknown leaves the setting empty, which needs Allow null checked."


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


def strips_typed_strings(*, item: bool) -> bool:
    """Return whether the admin strips spaces from the ends of a string typed in a single-line input.

    This applies to ``str`` values, the items of ``list:str`` and ``set:str``, and custom types without a ``form``.
    Follows ``DYNAMIC_CONFIGS["STRIP_STRINGS"]``: ``True`` strips single values and list items, ``False`` neither, and
    ``None`` (the default) single values only.

    :param item: whether the string is one item of a list or set, rather than a single value
    :rtype: bool
    """
    setting = get_settings()["STRIP_STRINGS"]
    if setting is None:
        return not item
    return bool(setting)


def formfield_for(
    config_type: ConfigType, *, allow_null: bool = False, item: bool = False, **kwargs: Any
) -> forms.Field:
    """Return the form field for editing a value of ``config_type``.

    :param config_type: the config's type
    :param allow_null: whether the config may be empty; a boolean then gets a three-way (yes/no/unknown) field
    :param item: whether the field edits one item of a list or set (the admin's item editor), which decides whether a
        typed string is stripped (``STRIP_STRINGS``, which covers only ``str`` and custom types without a ``form``)
    :param kwargs: options for the field, such as ``required``, ``label`` and ``help_text``
    :returns: a ``TypedLineListField`` for list and set types, the type's ``form_class``, or a ``SerializerField``
    :rtype: forms.Field
    """
    if config_type.container is not None:
        unique = config_type.container == "set"
        # The item editor and the raw textarea each show their own help (see TypedLineListField); under the field goes
        # only what's true of both.
        kwargs["help_text"] = SET_HELP if unique else ""
        return TypedLineListField(config_type.item_type, unique=unique, **kwargs)
    form_class = config_type.form_class
    if form_class is None:
        field: forms.Field = SerializerField(config_type.serializer, **kwargs)
        # A custom type without a form gets a plain text input, which follows STRIP_STRINGS.
        field.strip = strips_typed_strings(item=item)
        return field
    if config_type.key == "bool" and form_class is forms.BooleanField:
        # The built-in type's help describes typed text ("true or false (yes/no, …)"), which list items take but a
        # checkbox or select doesn't; a custom type's own help is its author's.
        kwargs["help_text"] = _NULL_BOOLEAN_HELP if allow_null else _BOOLEAN_HELP
    if allow_null and form_class is forms.BooleanField:
        # A checkbox can't be empty, so a boolean that allows None needs a yes/no/unknown choice.
        form_class = forms.NullBooleanField
    field = form_class(**kwargs)
    if config_type.key == "str" and form_class is forms.CharField:
        # Only the built-in str follows STRIP_STRINGS; every other type's own form field (a custom form, a duration,
        # multi-line text, a project's replacement str with its own form) keeps its own strip.
        field.strip = strips_typed_strings(item=item)
    return field
