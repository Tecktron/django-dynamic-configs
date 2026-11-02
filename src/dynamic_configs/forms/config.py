"""The admin's model forms for adding and changing configs.

Both forms turn the submitted value into stored text with ``ConfigType.to_text``, so an admin save passes the same type
check and serializer as the API, and apply the empty-value rules using the ``allow_null`` submitted in the same save.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

from dynamic_configs.exceptions import ConfigError, ConfigValueError
from dynamic_configs.forms.fields import formfield_for
from dynamic_configs.forms.list import TypedLineListField
from dynamic_configs.models import Config
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.registry import Registry, get_registry
from dynamic_configs.types.serializers import ListSerializer


def types_help_text(registry: Registry) -> SafeString:
    """Return the add page's help for the value: each base type's text format, then the list and set rule."""
    formats = format_html_join(
        "",
        "<br>{}: {}",
        ((config_type.label, config_type.help_text) for config_type in registry if config_type.container is None),
    )
    return format_html(
        "Enter the value as text for the chosen type.{}<br>Lists and sets: one item per line; sets don't allow "
        "repeats.",
        formats,
    )


class _ConfigForm(forms.ModelForm):
    """Shared handling of the value: the empty-value rules, then the type check and serializer."""

    def stored_text(self, config_type: ConfigType, value: Any, *, allow_null: bool) -> str | None:
        """Return the text to store for ``value``, applying the empty-value rules.

        :raises ValidationError: the value is empty but required, or the type rejects it
        """
        empty = value is None or value == "" or (config_type.container is not None and value == [])
        if empty:
            if allow_null:
                return None
            if config_type.container is not None:
                value = []
            elif config_type.python_type is str:
                value = ""
            else:
                raise ValidationError(self.fields["value"].error_messages["required"], code="required")
        try:
            return config_type.to_text(value)
        except ConfigError as error:
            raise ValidationError(str(error)) from error


class ConfigAddForm(_ConfigForm):
    """The add page: a name, a type, and the value as text, cleaned for the chosen type."""

    type = forms.ChoiceField(label="Type")
    # strip=False: whitespace can matter (multi-line text); each type's parser strips where it should.
    value = forms.CharField(widget=forms.Textarea(attrs={"class": "vLargeTextField"}), required=False, strip=False)

    class Meta:
        """Fields shown on the add page."""

        model = Config
        fields = ("name", "type", "value", "allow_null", "description")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Offer the registered types, and explain each type's text format."""
        super().__init__(*args, **kwargs)
        registry = get_registry()
        self.fields["type"].choices = [(config_type.key, config_type.label) for config_type in registry]
        self.fields["value"].help_text = types_help_text(registry)

    def clean(self) -> dict[str, Any]:
        """Parse the value text for the chosen type and replace it with the text to store."""
        cleaned = super().clean()
        config_type = get_registry().get(cleaned.get("type", ""))
        if config_type is None:
            # The type field has already reported an invalid choice.
            return cleaned
        try:
            value = self.parse_text(config_type, cleaned["value"])
            cleaned["value"] = self.stored_text(config_type, value, allow_null=cleaned.get("allow_null", False))
        except ValidationError as error:
            self.add_error("value", error)
        return cleaned

    @staticmethod
    def parse_text(config_type: ConfigType, text: str) -> Any:
        """Return the value written in ``text``: one item per line for lists and sets, the serializer otherwise."""
        if text == "":
            return None
        if config_type.container is not None:
            field = TypedLineListField(config_type.item_type, unique=config_type.container == "set")
            return field.to_python(text)
        try:
            return config_type.from_text(text)
        except ConfigValueError as error:
            raise ValidationError(str(error)) from error


class ConfigChangeForm(_ConfigForm):
    """The change page; ``change_form_for`` adds the value field for the config's type."""

    config_type: ConfigType | None = None

    class Meta:
        """Fields edited on the change page (name and type are read-only there)."""

        model = Config
        fields = ("value", "allow_null", "description")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Show the stored value as its type's field expects it."""
        super().__init__(*args, **kwargs)
        if self.config_type is not None and self.instance.value is not None:
            self.initial["value"] = self.initial_value(self.config_type, self.instance.value)

    @staticmethod
    def initial_value(config_type: ConfigType, text: str) -> Any:
        """Return the stored ``text`` as a value for the form; None when it can't be read, so the page still opens."""
        try:
            if config_type.container is not None:
                # Keep the stored order (a set would lose it), so the admin sees items as they were entered.
                return ListSerializer.deserialize(config_type.serializer, text)
            return config_type.from_text(text)
        except (ConfigValueError, ValueError):
            return None

    def clean(self) -> dict[str, Any]:
        """Replace the cleaned value with the text to store."""
        cleaned = super().clean()
        if self.config_type is not None and "value" in cleaned:
            try:
                cleaned["value"] = self.stored_text(
                    self.config_type, cleaned["value"], allow_null=cleaned.get("allow_null", False)
                )
            except ValidationError as error:
                self.add_error("value", error)
        return cleaned


def change_form_for(config: Config) -> type[ConfigChangeForm]:
    """Return the change form for ``config``: its type's field as ``value``, or the plain form if it's unregistered.

    :param config: the config being changed
    :rtype: type[ConfigChangeForm]
    """
    config_type = get_registry().get(config.type)
    if config_type is None:
        return ConfigChangeForm
    field = formfield_for(
        config_type,
        allow_null=config.allow_null,
        # Never required here: the empty-value rules in clean() decide, using the allow_null submitted with it.
        required=False,
        label="Value",
        help_text=config_type.help_text,
    )
    return type("ConfigChangeForm", (ConfigChangeForm,), {"value": field, "config_type": config_type})
