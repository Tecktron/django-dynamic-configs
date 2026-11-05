"""The admin's model forms for adding and changing configs.

Adding takes two steps: ``ConfigTypeForm`` chooses the type, then ``add_form_for`` gives the add form with that type's
value field, the same field the change page uses. Both turn the value into stored text with ``ConfigType.to_text``, so
an admin save passes the same type check and serializer as the API, and apply the empty-value rules using the
``allow_null`` submitted in the same save.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.exceptions import ConfigError
from dynamic_configs.forms.fields import formfield_for
from dynamic_configs.models import Config
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.registry import get_registry
from dynamic_configs.types.serializers import ListSerializer

# The admin's optional script (static/dynamic_configs/admin.js): every page works without it.
ADMIN_SCRIPT = "dynamic_configs/admin.js"


class _ConfigForm(forms.ModelForm):
    """Shared handling of the value: the empty-value rules, then the type check and serializer."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Keep descriptions exactly as typed (Django strips text fields by default)."""
        super().__init__(*args, **kwargs)
        # A skin may leave the description out of its fieldsets.
        if "description" in self.fields:
            self.fields["description"].strip = False

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


class ConfigTypeForm(forms.ModelForm):
    """The add page's first step: the type, whose value field the second step shows."""

    type = forms.ChoiceField(
        label="Type",
        help_text="Choose the type, then click Save to enter the value.",
        widget=forms.Select(attrs={"data-dynamic-configs-type": True}),
    )

    class Meta:
        """The only field on the first step."""

        model = Config
        fields = ("type",)

    class Media:
        """The optional script moves on as soon as a type is chosen."""

        js = (ADMIN_SCRIPT,)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Offer the registered types after a blank, so choosing any of them is a change the script can act on."""
        super().__init__(*args, **kwargs)
        self.fields["type"].choices = [("", "---------")] + [
            (config_type.key, config_type.label) for config_type in get_registry()
        ]


class _TypedConfigForm(_ConfigForm):
    """A form whose value field is its config type's; ``add_form_for`` and ``change_form_for`` set both."""

    config_type: ConfigType | None = None

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


class ConfigAddForm(_TypedConfigForm):
    """The add page's second step: the name and the value, for the type chosen in the first step."""

    # Always set: add_form_for builds every add form.
    config_type: ConfigType

    class Meta:
        """Fields entered on the add page (the type is shown read-only)."""

        model = Config
        fields = ("name", "value", "allow_null", "description")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Give the new config its type, so the page can show it and the save stores it."""
        super().__init__(*args, **kwargs)
        self.instance.type = self.config_type.key


class ConfigChangeForm(_TypedConfigForm):
    """The change page; ``change_form_for`` adds the value field for the config's type."""

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
        except Exception:
            # Whatever reading it raises (a RecursionError on JSON nested too deeply, a custom serializer's KeyError),
            # as from_text treats it for get(): the stored text is unreadable, and the admin needs the page to fix it.
            return None


def _value_field(config_type: ConfigType, *, allow_null: bool) -> forms.Field:
    """Return the value field for ``config_type``, as both pages show it."""
    return formfield_for(
        config_type,
        allow_null=allow_null,
        # Never required here: the empty-value rules in clean() decide, using the allow_null submitted with it.
        required=False,
        label="Value",
        help_text=config_type.help_text,
    )


def add_form_for(config_type: ConfigType) -> type[ConfigAddForm]:
    """Return the add form for a new config of ``config_type``.

    :param config_type: the type chosen in the first step
    :rtype: type[ConfigAddForm]
    """
    # allow_null=True: whether the config allows None isn't known until it's saved, so a boolean gets the
    # yes/no/unknown choice and the empty-value rules decide.
    field = _value_field(config_type, allow_null=True)
    return type("ConfigAddForm", (ConfigAddForm,), {"value": field, "config_type": config_type})


def change_form_for(config: Config) -> type[ConfigChangeForm]:
    """Return the change form for ``config``: its type's field as ``value``, or the plain form if it's unregistered.

    :param config: the config being changed
    :rtype: type[ConfigChangeForm]
    """
    config_type = get_registry().get(config.type)
    if config_type is None:
        return ConfigChangeForm
    field = _value_field(config_type, allow_null=config.allow_null)
    return type("ConfigChangeForm", (ConfigChangeForm,), {"value": field, "config_type": config_type})
