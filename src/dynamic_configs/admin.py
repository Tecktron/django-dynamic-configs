"""Django admin for configs.

The admin ships no templates of its own, only Django's admin widgets, an optional script, the JSON and list editors'
optional scripts and their stylesheet (which styles only the editors' own elements), so admin skins apply. All of the
behaviour is in ``ConfigAdminMixin``, including the list editor's check URL: skins with their own ``ModelAdmin`` base
unregister ``ConfigAdmin`` and register ``ConfigAdminMixin`` combined with their base.
"""

from __future__ import annotations

import json
from typing import Any, cast

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import widgets as admin_widgets
from django.contrib.admin.utils import quote, unquote
from django.core import checks
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, router, transaction
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
    JsonResponse,
)
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.text import Truncator

from dynamic_configs.conf import get_settings
from dynamic_configs.constants import ADMIN_SCRIPT, LIST_PREFIX, SET_PREFIX
from dynamic_configs.forms.config import ConfigTypeForm, add_form_for, change_form_for
from dynamic_configs.forms.datetime import ZonedDateTimeWidget
from dynamic_configs.forms.fields import formfield_for
from dynamic_configs.forms.json import JSONTextarea
from dynamic_configs.forms.list import ListWidget, TypedLineListField, stored_texts
from dynamic_configs.forms.money import CurrencyInput
from dynamic_configs.models import Config
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.registry import get_registry
from dynamic_configs.types.serializers import JSONSerializer

_STYLESHEET = "dynamic_configs/admin.css"


class AdminZonedDateTimeWidget(ZonedDateTimeWidget):
    """The zoned datetime widget with the admin's date and time pickers."""

    date_widget = admin_widgets.AdminDateWidget
    time_widget = admin_widgets.AdminTimeWidget

    class Media:
        """The optional script starts an empty value on the browser's zone and keeps the pickers in the chosen one."""

        js = (ADMIN_SCRIPT,)


class AdminIntegerInput(forms.NumberInput):
    """A whole number's input, marked for the admin script, which trims a decimal typed into it to its whole part."""

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Keep ``attrs`` (the field's min, max and step) and add the mark."""
        super().__init__(attrs={**(attrs or {}), "data-dynamic-configs-int": True})

    class Media:
        """The admin script, which keeps the input to whole numbers."""

        js = (ADMIN_SCRIPT,)


class AdminDecimalInput(forms.NumberInput):
    """A decimal's input (money's too), marked for the admin script, which steps it from multiples of its step."""

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Keep ``attrs`` (the field's min, max and step) and add the mark."""
        super().__init__(attrs={**(attrs or {}), "data-dynamic-configs-decimal": True})

    class Media:
        """The admin script, which counts the arrows' steps from multiples of the step."""

        js = (ADMIN_SCRIPT,)


class AdminCurrencyInput(CurrencyInput):
    """Money's currency input, marked for the suggestions script, which shows the datalist as the admin's dropdown."""

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Keep ``attrs`` (its size and length) and add the mark."""
        super().__init__(attrs={**(attrs or {}), "data-dynamic-configs-suggest": True})

    class Media:
        """The suggestions script, and the stylesheet with the dropdown's look."""

        js = ("dynamic_configs/suggestions.js",)
        css = {"all": (_STYLESHEET,)}


class AdminJSONTextarea(admin_widgets.AdminTextareaWidget):
    """The admin's textarea for JSON: the editor script formats, checks and colours it as it's typed."""

    class Media:
        """The editor's script, and the stylesheet with its colours."""

        js = ("dynamic_configs/json_editor.js",)
        css = {"all": (_STYLESHEET,)}


class AdminListEditorWidget(ListWidget):
    """The list editor: the raw textarea, plus the item editor (the item type's own input) for the editor script.

    The item editor is rendered hidden with the page, so Django's widget scripts (the date picker, the admin script's
    zone links) attach to it as to any field; the script shows it and fills its inputs in. Its field's help goes with
    it, as ``raw_help`` goes with the textarea, so each shows only while its input does.
    """

    _LIST_EDITOR_SCRIPT = "dynamic_configs/list_editor.js"
    # The item editor's inputs are named after the field with this suffix.
    ITEM_SUFFIX = "__item"

    def __init__(
        self,
        attrs: dict[str, Any] | None = None,
        *,
        raw_help: str,
        item_field: forms.Field,
        check_url: str,
        sortable: bool,
        unique: bool,
    ) -> None:
        """Keep the item editor's field, the check URL, and whether the list sorts and is a set."""
        super().__init__(attrs={"class": "vLargeTextField", **(attrs or {})}, raw_help=raw_help)
        self.item_field = item_field
        self.check_url = check_url
        self.sortable = sortable
        self.unique = unique

    @property
    def media(self) -> forms.Media:
        """The item editor's own scripts first (the date picker, say), then the list editor's script and stylesheet."""
        return self.item_field.widget.media + forms.Media(js=[self._LIST_EDITOR_SCRIPT], css={"all": [_STYLESHEET]})

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> SafeString:
        """Render the raw textarea and hidden inputs, and the item editor, marked for the editor script."""
        editor = self.item_field.widget.render(
            f"{name}{self.ITEM_SUFFIX}", None, {"id": f"id_{name}{self.ITEM_SUFFIX}"}, renderer
        )
        help_text = self.item_field.help_text
        return format_html(
            '<div class="dynamic-configs-list" data-dynamic-configs-list data-name="{}" data-check-url="{}" '
            'data-set="{}" data-sortable="{}">{}<div class="dynamic-configs-list-item" hidden>{}{}</div></div>',
            name,
            self.check_url,
            "true" if self.unique else "false",
            "true" if self.sortable else "false",
            super().render(name, value, attrs, renderer),
            editor,
            format_html('<p class="help">{}</p>', help_text) if help_text else "",
        )


class ConfigAdminMixin:
    """The config admin's behaviour; combine it with ``admin.ModelAdmin`` or a skin's ``ModelAdmin``.

    The mixin sets the fields and their layout itself (``get_fieldsets``: the type alone on the add page's first step,
    then every field) and which of them are read-only (``get_readonly_fields``: the type once chosen, the name once
    created). So the ``fields``, ``fieldsets`` and ``readonly_fields`` options are ignored, and the system check
    ``dynamic_configs.W001`` warns when one is set. To change them, override those methods and call ``super()``.

    Put the mixin first among an admin's base classes: ``dynamic_configs.E006`` reports a base before it whose
    ``history_form_view`` would run instead of the mixin's.
    """

    _PREVIEW_LENGTH = 80
    _FIELDS = ("name", "type", "value", "allow_null", "description")
    _LIST_ITEM_URL = "dynamic_configs_config_list_item"
    _UNREADABLE = "The request couldn't be read. Reload the page and try again."

    class _NameTaken(IntegrityError):  # noqa: N818 - an IntegrityError, so one that escapes looks like the original
        """The add found its name taken when it saved: another save created it after the form checked."""

    # ModelAdmin options this mixin's methods replace (see the class docstring).
    _IGNORED_OPTIONS = ("fields", "fieldsets", "readonly_fields")
    # Django's plain widgets (and the zoned datetime widget) mapped to the admin's versions (date picker, split
    # date/time, styled textarea). Matched by exact type, so a type's own widget is never replaced, even one that
    # subclasses Textarea (as code editors do).
    _ADMIN_WIDGETS: dict[type[forms.Widget], type[forms.Widget]] = {
        forms.DateInput: admin_widgets.AdminDateWidget,
        forms.SplitDateTimeWidget: admin_widgets.AdminSplitDateTime,
        ZonedDateTimeWidget: AdminZonedDateTimeWidget,
        forms.Textarea: admin_widgets.AdminTextareaWidget,
        JSONTextarea: AdminJSONTextarea,
    }
    # A combined field's parts the package owns, mapped to the admin's versions; matched by exact type, as above.
    _ADMIN_PARTS: dict[type[forms.Widget], type[forms.Widget]] = {CurrencyInput: AdminCurrencyInput}

    list_display = ("name", "type_label", "value_preview", "description", "modified_on")
    list_filter = ("type",)
    search_fields = ("name", "description")
    ordering = ("name",)

    @classmethod
    def _number_widget_class(cls, field: forms.Field, widget: forms.Widget) -> type[forms.Widget] | None:
        """Return the admin's number input for ``widget`` (``field``'s input, or a part of it), or None to keep it.

        A number input is swapped for a decimal field (money's too) and a whole-number field, each with its own mark.
        Float and decimal fields use the same input as whole numbers, and Django makes them subclasses of
        ``IntegerField``; a float's input is left as it is.
        """
        if type(widget) is not forms.NumberInput:
            return None
        if isinstance(field, forms.DecimalField):
            return AdminDecimalInput
        if isinstance(field, forms.IntegerField) and not isinstance(field, forms.FloatField):
            return AdminIntegerInput
        return None

    @classmethod
    def _use_admin_widget(cls, field: forms.Field) -> None:
        """Swap ``field``'s widget for the admin's version when it's one of Django's plain widgets, keeping its attrs.

        A combined field (``MultiValueField``) whose widget has one input per field gets the number inputs among them
        marked the same way, and money's currency input (``CurrencyInput``) gets the admin's dropdown; its other parts
        are a project's own and stay as they are.
        """
        widget_class = cls._ADMIN_WIDGETS.get(type(field.widget)) or cls._number_widget_class(field, field.widget)
        if widget_class is not None:
            field.widget = widget_class(attrs=field.widget.attrs)
        elif isinstance(field, forms.MultiValueField) and isinstance(field.widget, forms.MultiWidget):
            parts = field.widget.widgets
            if len(parts) == len(field.fields):
                for index, (part_field, part) in enumerate(zip(field.fields, parts, strict=True)):
                    part_class = cls._number_widget_class(part_field, part) or cls._ADMIN_PARTS.get(type(part))
                    if part_class is not None:
                        parts[index] = part_class(attrs=part.attrs)

    @staticmethod
    def _chosen_type(request: HttpRequest) -> ConfigType | None:
        """Return the type chosen in the add page's first step (``?type=`` in the address), or None."""
        return get_registry().get(request.GET.get("type", ""))

    @classmethod
    def _texts(cls, raw: str | None) -> list[str]:
        """Return the JSON array of strings the list editor sent; raise ValidationError when it isn't one."""
        texts = None
        # A flat array of strings: refuse nesting before json.loads, which can run out of stack on it.
        if not JSONSerializer.nests_deeper_than(raw or "", 1):
            try:
                texts = json.loads(raw or "")
            except ValueError:
                pass
        if not isinstance(texts, list) or not all(isinstance(text, str) for text in texts):
            raise ValidationError(cls._UNREADABLE)
        return texts

    @classmethod
    def _position(cls, raw: str | None) -> int | None:
        """Return the item's index the list editor sent, or None for a new item (empty or missing).

        Only 1 to 9 ASCII digits are an index: ``int()`` refuses some digits (``"²"``) and very long strings.
        Raise ValidationError for anything else.
        """
        if not raw:
            return None
        if not (raw.isascii() and raw.isdigit() and len(raw) <= 9):
            raise ValidationError(cls._UNREADABLE)
        return int(raw)

    def check(self, **kwargs: Any) -> list[checks.CheckMessage]:
        """Run the admin's checks, and add the mixin's own: W001 and E006.

        W001 warns about each option the mixin ignores because it sets it itself. E006 reports a base class placed
        before the mixin whose ``history_form_view`` would run instead of the mixin's.
        """
        found = list(super().check(**kwargs))  # type: ignore[misc]
        mro = type(self).__mro__
        # A base before the mixin (SimpleHistoryAdmin, say) whose history_form_view runs instead of the mixin's.
        shadowing = next(
            (
                base
                for base in mro[: mro.index(ConfigAdminMixin)]
                if "history_form_view" in vars(base) and not issubclass(base, ConfigAdminMixin)
            ),
            None,
        )
        if shadowing is not None:
            found.append(
                checks.Error(
                    f"{type(self).__name__} puts {shadowing.__name__} before ConfigAdminMixin, so its "
                    "history_form_view runs instead of ConfigAdminMixin's.",
                    hint="Put ConfigAdminMixin first among the base classes, as in "
                    "class ConfigAdmin(ConfigAdminMixin, SimpleHistoryAdmin, ModelAdmin).",
                    obj=type(self),
                    id="dynamic_configs.E006",
                )
            )
        for option in self._IGNORED_OPTIONS:
            # Django's defaults for these are empty (None or ()).
            if getattr(self, option):
                found.append(
                    checks.Warning(
                        f"{type(self).__name__} sets {option}, which ConfigAdminMixin ignores: it sets them itself.",
                        hint="Override get_fieldsets() or get_readonly_fields() and call super().",
                        obj=type(self),
                        id="dynamic_configs.W001",
                    )
                )
        return found

    def get_fieldsets(self, request: HttpRequest, obj: Config | None = None) -> list[tuple[Any, dict[str, Any]]]:
        """Show the type alone on the add page's first step, and the same fields on every other page."""
        if obj is None and self._chosen_type(request) is None:
            return [(None, {"fields": ("type",)})]
        return [(None, {"fields": self._FIELDS})]

    def get_readonly_fields(self, request: HttpRequest, obj: Config | None = None) -> tuple[str, ...]:
        """Lock the type once chosen, the name once created, and the value when its type isn't registered."""
        if obj is None:
            return () if self._chosen_type(request) is None else ("type",)
        if get_registry().get(obj.type) is None:
            return ("name", "type", "value")
        return ("name", "type")

    def get_form(self, request: HttpRequest, obj: Config | None = None, change: bool = False, **kwargs: Any) -> Any:
        """Use the type step, the add form for the chosen type, or the change form for the config's type."""
        if obj is not None:
            kwargs["form"] = change_form_for(obj)
        else:
            config_type = self._chosen_type(request)
            kwargs["form"] = ConfigTypeForm if config_type is None else add_form_for(config_type)
        form = super().get_form(request, obj, change, **kwargs)  # type: ignore[misc]
        if "value" in form.base_fields:
            field = form.base_fields["value"]
            self._use_admin_widget(field)
            if isinstance(field, TypedLineListField):
                self._use_list_editor(field)
        return form

    def _use_list_editor(self, field: TypedLineListField) -> None:
        """Give a list or set value the list editor, pointed at this admin's check URL."""
        key = f"{SET_PREFIX if field.unique else LIST_PREFIX}{field.item_type.key}"
        self._use_admin_widget(field.item_field)
        field.widget = AdminListEditorWidget(
            attrs=field.widget.attrs,
            raw_help=cast(ListWidget, field.widget).raw_help,
            item_field=field.item_field,
            check_url=reverse(f"{self.admin_site.name}:{self._LIST_ITEM_URL}", args=[key]),  # type: ignore[attr-defined]
            # Sets are unordered, so they have no Sort (nor Up and Down).
            sortable=not field.unique and field.item_type.sortable,
            unique=field.unique,
        )

    def add_view(
        self, request: HttpRequest, form_url: str = "", extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        """Ask for the type first, then show the add page with that type's value field (``?type=`` in the address)."""
        if self._chosen_type(request) is not None:
            # Post the second step back to its own query. Left empty, Django points the form at the list's preserved
            # filters alone (after a search, say), which drops type= and sends the save back to the first step.
            form_url = form_url or f"?{request.GET.urlencode()}"
        else:
            if request.method == "POST":
                form = ConfigTypeForm(request.POST)
                if form.is_valid():
                    # Keep the rest of the query (a popup's, say), so the second step behaves like the first.
                    query = request.GET.copy()
                    query["type"] = form.cleaned_data["type"]
                    return HttpResponseRedirect(f"{request.path}?{query.urlencode()}")
            # The first step saves nothing, so only its Save button (which moves on) applies.
            extra_context = {
                **(extra_context or {}),
                "show_save_and_add_another": False,
                "show_save_and_continue": False,
            }
        try:
            return super().add_view(request, form_url, extra_context)  # type: ignore[misc]
        except self._NameTaken:
            # The name was taken between the form's check and the save. The save is undone, and the form checks again
            # now that the row exists, so the page says what it always does: a config with that name already exists.
            return super().add_view(request, form_url, extra_context)  # type: ignore[misc]

    def save_model(self, request: HttpRequest, obj: Config, form: forms.ModelForm, change: bool) -> None:  # type: ignore[type-arg]
        """Save as Django does, but an add only inserts, so a name taken meanwhile is never overwritten.

        The insert runs in a savepoint: a failure is undone alone, and the request's own transaction (the admin's, or
        ``ATOMIC_REQUESTS``) stays usable. Only an ``IntegrityError`` is caught, and only when a row with the name
        exists now; anything else is raised as it was.

        :raises _NameTaken: the name was taken after the form checked it
        """
        if change:
            super().save_model(request, obj, form, change)  # type: ignore[misc]
            return
        # Django's save updates a row that has the primary key before it inserts, so it would overwrite one. Only the
        # first save is forced: the wrapper removes itself, so a post_save receiver that saves again updates as usual.
        original = obj.save

        def insert_once(*args: Any, **kwargs: Any) -> None:
            vars(obj).pop("save", None)
            original(*args, force_insert=True, **kwargs)

        obj.save = insert_once  # type: ignore[method-assign]
        using = router.db_for_write(self.model)  # type: ignore[attr-defined]
        try:
            with transaction.atomic(using=using):
                super().save_model(request, obj, form, change)  # type: ignore[misc]
        except IntegrityError as error:
            if not self.model._default_manager.using(using).filter(pk=obj.pk).exists():  # type: ignore[attr-defined]
                raise
            raise self._NameTaken from error
        finally:
            vars(obj).pop("save", None)

    def change_view(
        self, request: HttpRequest, object_id: str, form_url: str = "", extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        """Warn when the config's type isn't registered, so its value can't be edited.

        Only on GET: a save's warning would show again on the page it leads to, beside that page's own.
        """
        if request.method != "GET":
            return super().change_view(request, object_id, form_url, extra_context)  # type: ignore[misc]
        config = self.get_object(request, unquote(object_id))  # type: ignore[attr-defined]
        # Only for a user who may see the config: the warning names its type, and a refused user gets no message.
        if (
            config is not None
            and get_registry().get(config.type) is None
            and self.has_view_or_change_permission(request, config)  # type: ignore[attr-defined]
        ):
            self.message_user(  # type: ignore[attr-defined]
                request,
                f"This config's type {config.type!r} isn't registered, so its value can't be edited. "
                "Add the type to DYNAMIC_CONFIGS['TYPES'].",
                messages.WARNING,
            )
        return super().change_view(request, object_id, form_url, extra_context)  # type: ignore[misc]

    def history_form_view(
        self, request: HttpRequest, object_id: str, version_id: str, extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        """Check a revert from django-simple-history's page of a past version, then leave the page to it.

        Only ``SimpleHistoryAdmin`` routes here; with a plain ``ModelAdmin``, Django never calls it. A GET only shows
        the version, so it's simple-history's alone. A POST restores the version, so it's refused (403) when
        ``SIMPLE_HISTORY_REVERT_DISABLED`` is set, when the admin's ``revert_disabled()`` returns True, or when the
        user can't change the config, or can't add it when it has been deleted (reverting re-creates it). A version
        whose type isn't the config's, or isn't registered, isn't restored: a config's type never changes.
        """
        if request.method == "POST":
            refusal = self._refuse_revert(request, object_id, version_id)
            if refusal is not None:
                return refusal
        return super().history_form_view(request, object_id, version_id, extra_context)  # type: ignore[misc]

    def _refuse_revert(self, request: HttpRequest, object_id: str, version_id: str) -> HttpResponse | None:
        """Return a redirect with a message when the version's type rules out the revert, or None to allow it.

        Raise PermissionDenied when the user may not revert.
        """
        model = self.model  # type: ignore[attr-defined]
        history = getattr(model, model._meta.simple_history_manager_attribute)
        # Found as simple-history finds it, so this checks the version it saves. A missing one is left to its 404.
        version = history.filter(**{model._meta.pk.attname: object_id, "history_id": version_id}).first()
        if version is None:
            return None
        # Calls the admin's revert_disabled() (simple-history 3.8 and later have it) as simple-history calls it, with
        # the version's instance.
        revert_disabled = getattr(self, "revert_disabled", None)
        if getattr(settings, "SIMPLE_HISTORY_REVERT_DISABLED", False) or (
            revert_disabled is not None and revert_disabled(request, version.instance)
        ):
            raise PermissionDenied
        name = version.instance.pk
        # Read where the revert writes: it updates this row, or inserts it again when it's gone.
        live = model._default_manager.db_manager(router.db_for_write(model)).filter(pk=name).first()
        if live is not None:
            allowed = self.has_change_permission(request, live)  # type: ignore[attr-defined]
        else:
            allowed = self.has_add_permission(request)  # type: ignore[attr-defined]
        if not allowed:
            raise PermissionDenied
        if live is not None and version.type != live.type:
            message = (
                f"This version's type {version.type!r} isn't the config's type {live.type!r}, and a config's type "
                "never changes, so it wasn't restored."
            )
        elif get_registry().get(version.type) is None:
            message = (
                f"This version's type {version.type!r} isn't registered, so it wasn't restored. Add the type to "
                "DYNAMIC_CONFIGS['TYPES']."
            )
        else:
            return None
        self.message_user(request, message, messages.ERROR)  # type: ignore[attr-defined]
        opts = model._meta
        site = self.admin_site.name  # type: ignore[attr-defined]
        return HttpResponseRedirect(reverse(f"{site}:{opts.app_label}_{opts.model_name}_history", args=[quote(name)]))

    def get_urls(self) -> list[Any]:
        """Add the list editor's check URL, before the admin's own (whose ``<path:object_id>/`` would take it).

        Config names are UPPER_SNAKE_CASE, so ``list-item`` can't be a config's address.
        """
        view = self.admin_site.admin_view(self.list_item_view)  # type: ignore[attr-defined]
        return [path("list-item/<str:type_key>/", view, name=self._LIST_ITEM_URL), *super().get_urls()]  # type: ignore[misc]

    def list_item_view(self, request: HttpRequest, type_key: str) -> HttpResponse:
        """Answer the list editor: check an item, load one into the editor, check raw lines, or sort. Never saves.

        Behind the admin's login and CSRF check (``admin_view``), and needs add or change permission on configs, so only
        someone who can edit configs can ask. Every rule is the Python one: the script never checks items itself.
        """
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not (
            self.has_add_permission(request) or self.has_change_permission(request)  # type: ignore[attr-defined]
        ):
            raise PermissionDenied
        config_type = get_registry().get(type_key)
        if config_type is None or config_type.container is None:
            raise Http404("No list or set type has that key.")
        field = cast(TypedLineListField, formfield_for(config_type))
        self._use_admin_widget(field.item_field)
        post = request.POST
        name = post.get("name", "")
        try:
            match post.get("action"):
                case "check":
                    reply: dict[str, Any] = {
                        "text": field.item_text(
                            post,
                            request.FILES,
                            name,
                            others=self._texts(post.get("items")),
                            position=self._position(post.get("position")),
                        )
                    }
                case "load":
                    reply = {"values": field.editor_values(post.get("text", ""), name)}
                case "lines":
                    reply = {"texts": field.texts_from_lines(self._texts(post.get("lines")))}
                case "sort":
                    descending = post.get("direction") == "descending"
                    reply = {"texts": field.sorted_texts(self._texts(post.get("items")), descending=descending)}
                case _:
                    return HttpResponseBadRequest("Unknown action.")
        except ValidationError as error:
            return JsonResponse({"errors": error.messages})
        return JsonResponse(reply)

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
            texts = stored_texts(obj.value)
            # Not a JSON array of strings (a hand-edited row, say): show the stored text as it is.
            if texts is not None:
                text = ", ".join(texts)
        return Truncator(text).chars(self._PREVIEW_LENGTH)


class ConfigAdmin(ConfigAdminMixin, admin.ModelAdmin):
    """The default config admin."""


def register_admin(site: admin.AdminSite = admin.site) -> None:
    """Register ``ConfigAdmin`` on ``site`` unless ``DYNAMIC_CONFIGS["REGISTER_ADMIN"]`` is False.

    Calling it again does nothing, so integrations that replace the registration can call it first.
    """
    if get_settings()["REGISTER_ADMIN"] and not site.is_registered(Config):
        site.register(Config, ConfigAdmin)


register_admin()
