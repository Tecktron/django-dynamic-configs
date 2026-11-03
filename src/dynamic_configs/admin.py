"""Django admin for configs.

The admin ships no templates, CSS or JavaScript of its own, only Django's admin widgets, so admin skins apply. All of
the behaviour is in ``ConfigAdminMixin``: skins with their own ``ModelAdmin`` base unregister ``ConfigAdmin`` and
register ``ConfigAdminMixin`` combined with their base.
"""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import widgets as admin_widgets
from django.contrib.admin.utils import unquote
from django.http import HttpRequest, HttpResponse
from django.utils.text import Truncator

from dynamic_configs.conf import get_settings
from dynamic_configs.forms.config import ConfigAddForm, change_form_for
from dynamic_configs.models import Config
from dynamic_configs.types.registry import get_registry

_PREVIEW_LENGTH = 80
_FIELDS = ("name", "type", "value", "allow_null", "description")
# Django's plain widgets mapped to the admin's versions (date picker, split date/time, styled textarea). Matched by
# exact type, so a type's own widget is never replaced, even one that subclasses Textarea (as code editors do).
_ADMIN_WIDGETS: dict[type[forms.Widget], type[forms.Widget]] = {
    forms.DateInput: admin_widgets.AdminDateWidget,
    forms.SplitDateTimeWidget: admin_widgets.AdminSplitDateTime,
    forms.Textarea: admin_widgets.AdminTextareaWidget,
}


def _use_admin_widget(field: forms.Field) -> None:
    """Swap ``field``'s widget for the admin's version when it's one of Django's plain widgets, keeping its attrs."""
    widget_class = _ADMIN_WIDGETS.get(type(field.widget))
    if widget_class is not None:
        field.widget = widget_class(attrs=field.widget.attrs)


class ConfigAdminMixin:
    """The config admin's behaviour; combine it with ``admin.ModelAdmin`` or a skin's ``ModelAdmin``."""

    list_display = ("name", "type_label", "value_preview", "description", "modified_on")
    list_filter = ("type",)
    search_fields = ("name", "description")
    ordering = ("name",)

    def get_fieldsets(self, request: HttpRequest, obj: Config | None = None) -> list[tuple[Any, dict[str, Any]]]:
        """Show the same fields on the add and change pages."""
        return [(None, {"fields": _FIELDS})]

    def get_readonly_fields(self, request: HttpRequest, obj: Config | None = None) -> tuple[str, ...]:
        """Lock the name and type once created, and the value when its type isn't registered."""
        if obj is None:
            return ()
        if get_registry().get(obj.type) is None:
            return ("name", "type", "value")
        return ("name", "type")

    def get_form(self, request: HttpRequest, obj: Config | None = None, change: bool = False, **kwargs: Any) -> Any:
        """Use the add form, or a change form with the value field for the config's type."""
        kwargs["form"] = ConfigAddForm if obj is None else change_form_for(obj)
        form = super().get_form(request, obj, change, **kwargs)  # type: ignore[misc]
        if obj is not None and "value" in form.base_fields:
            _use_admin_widget(form.base_fields["value"])
        return form

    def change_view(
        self, request: HttpRequest, object_id: str, form_url: str = "", extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        """Warn when the config's type isn't registered, so its value can't be edited."""
        config = self.get_object(request, unquote(object_id))  # type: ignore[attr-defined]
        if config is not None and get_registry().get(config.type) is None:
            self.message_user(  # type: ignore[attr-defined]
                request,
                f"This config's type {config.type!r} isn't registered, so its value can't be edited. "
                "Add the type to DYNAMIC_CONFIGS['TYPES'].",
                messages.WARNING,
            )
        return super().change_view(request, object_id, form_url, extra_context)  # type: ignore[misc]

    @admin.display(description="type", ordering="type")
    def type_label(self, obj: Config) -> str:
        """Return the type's label, or its key marked as not registered."""
        config_type = get_registry().get(obj.type)
        return config_type.label if config_type is not None else f"{obj.type} (not registered)"

    @admin.display(description="value")
    def value_preview(self, obj: Config) -> str:
        """Return the stored value, shortened; list and set items are joined with commas."""
        if obj.value is None:
            return self.get_empty_value_display()  # type: ignore[attr-defined]
        text = obj.value
        config_type = get_registry().get(obj.type)
        if config_type is not None and config_type.container is not None:
            try:
                text = ", ".join(json.loads(obj.value))
            except (ValueError, TypeError):
                # Not a JSON array of strings (a hand-edited row, say): show the stored text as it is.
                text = obj.value
        return Truncator(text).chars(_PREVIEW_LENGTH)


class ConfigAdmin(ConfigAdminMixin, admin.ModelAdmin):
    """The default config admin."""


def register_admin(site: admin.AdminSite = admin.site) -> None:
    """Register ``ConfigAdmin`` on ``site`` unless ``DYNAMIC_CONFIGS["REGISTER_ADMIN"]`` is False.

    Calling it again does nothing, so integrations that replace the registration can call it first.
    """
    if get_settings()["REGISTER_ADMIN"] and not site.is_registered(Config):
        site.register(Config, ConfigAdmin)


register_admin()
