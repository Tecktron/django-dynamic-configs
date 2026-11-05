"""The type registry: built-in types, custom types from ``DYNAMIC_CONFIGS["TYPES"]``, and list and set variants."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from django import forms
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.module_loading import import_string

from dynamic_configs.conf import get_settings
from dynamic_configs.log import log
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.builtin import BUILTIN_TYPES
from dynamic_configs.types.serializers import ListSerializer, SetSerializer

logger = logging.getLogger(__name__)

LIST_PREFIX = "list:"
SET_PREFIX = "set:"
# No ":" allowed, because it marks list and set variants.
TYPE_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_ENTRY_KEYS = frozenset({"type", "serializer", "form", "label", "help_text", "listable"})


class TypeConfigError(ImproperlyConfigured):
    """A problem in ``DYNAMIC_CONFIGS["TYPES"]``, carrying the id of the system check that reports it."""

    def __init__(self, message: str, check_id: str) -> None:
        """Store the message and the check id (such as ``dynamic_configs.E002``)."""
        super().__init__(message)
        self.check_id = check_id


def load_custom_type(key: Any, entry: Any) -> ConfigType:
    """Return the ``ConfigType`` declared by one ``TYPES`` entry, importing its dotted paths.

    :param key: the type key, such as ``"color"``
    :param entry: the entry's dict (``type``, ``serializer`` and optionally ``form``, ``label``, ``help_text``,
        ``listable``)
    :returns: the loaded type
    :rtype: ConfigType
    :raises TypeConfigError: the entry is invalid; ``check_id`` says which system check reports it
    """
    where = f"DYNAMIC_CONFIGS['TYPES'][{key!r}]"
    if not isinstance(key, str) or not TYPE_KEY_RE.fullmatch(key):
        raise TypeConfigError(
            f"{where}: type keys must start with a letter and contain only letters, digits and underscores.",
            "dynamic_configs.E001",
        )
    if not isinstance(entry, Mapping):
        raise TypeConfigError(f"{where} must be a dict.", "dynamic_configs.E001")
    unknown = sorted(repr(name) for name in set(entry) - _ENTRY_KEYS)
    if unknown:
        raise TypeConfigError(f"{where} has unknown keys: {', '.join(unknown)}.", "dynamic_configs.E001")
    for required in ("type", "serializer"):
        if not isinstance(entry.get(required), str):
            raise TypeConfigError(f"{where}[{required!r}] must be a dotted path string.", "dynamic_configs.E001")
    python_type = _import(where, "type", entry["type"])
    if not isinstance(python_type, type):
        raise TypeConfigError(f"{where}['type'] must be a class.", "dynamic_configs.E001")
    serializer = _load_serializer(where, entry["serializer"])
    form_class = _load_form(where, entry["form"]) if "form" in entry else None
    label = entry.get("label", key)
    help_text = entry.get("help_text", "")
    listable = entry.get("listable", True)
    if not isinstance(label, str) or not isinstance(help_text, str) or not isinstance(listable, bool):
        raise TypeConfigError(
            f"{where}: 'label' and 'help_text' must be strings and 'listable' a boolean.", "dynamic_configs.E001"
        )
    return ConfigType(
        key=key,
        label=label,
        python_type=python_type,
        serializer=serializer,
        help_text=help_text,
        listable=listable,
        form_class=form_class,
    )


def _import(where: str, field: str, path: str) -> Any:
    """Import ``path``, raising TypeConfigError (E002) when it can't be imported, whatever importing it raises."""
    try:
        return import_string(path)
    except Exception as error:
        # Not only ImportError: a module that fails while it's imported (a NameError, say) is just as unusable, and
        # letting it escape would stop the non-strict build, and so every config read.
        raise TypeConfigError(
            f"{where}[{field!r}]: can't import {path!r} ({type(error).__name__}: {error}).", "dynamic_configs.E002"
        ) from error


def _load_serializer(where: str, path: str) -> Any:
    """Import the serializer class at ``path`` and create it with no arguments."""
    serializer_class = _import(where, "serializer", path)
    if not isinstance(serializer_class, type):
        raise TypeConfigError(f"{where}['serializer'] must be a class.", "dynamic_configs.E003")
    try:
        serializer = serializer_class()
    except Exception as error:
        raise TypeConfigError(
            f"{where}['serializer']: {path!r} must be creatable with no arguments ({error}).", "dynamic_configs.E003"
        ) from error
    if not (callable(getattr(serializer, "serialize", None)) and callable(getattr(serializer, "deserialize", None))):
        raise TypeConfigError(
            f"{where}['serializer']: {path!r} needs serialize() and deserialize() methods.", "dynamic_configs.E003"
        )
    return serializer


def _load_form(where: str, path: Any) -> type:
    """Import the form field class at ``path``."""
    if not isinstance(path, str):
        raise TypeConfigError(f"{where}['form'] must be a dotted path string.", "dynamic_configs.E001")
    form_class = _import(where, "form", path)
    if not (isinstance(form_class, type) and issubclass(form_class, forms.Field)):
        raise TypeConfigError(f"{where}['form'] must be a django.forms.Field subclass.", "dynamic_configs.E004")
    return form_class


def _variant_help(prefix: str, item: ConfigType) -> str:
    """Return a list or set variant's help text, built from its item type's."""
    return f"{prefix} Each item: {item.help_text}" if item.help_text else prefix


def list_variant(item: ConfigType) -> ConfigType:
    """Return the list variant of ``item`` (key ``list:<key>``)."""
    return ConfigType(
        key=f"{LIST_PREFIX}{item.key}",
        label=f"List of {item.label}",
        python_type=list,
        serializer=ListSerializer(item.serializer),
        help_text=_variant_help("One item per line.", item),
        listable=False,
        item_type=item,
        container="list",
    )


def set_variant(item: ConfigType) -> ConfigType:
    """Return the set variant of ``item`` (key ``set:<key>``); ``item`` must be hashable."""
    return ConfigType(
        key=f"{SET_PREFIX}{item.key}",
        label=f"Set of {item.label}",
        python_type=frozenset,
        serializer=SetSerializer(item.serializer),
        help_text=_variant_help("One item per line, with no repeats.", item),
        listable=False,
        item_type=item,
        container="set",
    )


class Registry:
    """The registered config types, looked up by key."""

    def __init__(self, types: Iterable[ConfigType]) -> None:
        """Index ``types`` by key."""
        self._types = {config_type.key: config_type for config_type in types}

    def get(self, key: str) -> ConfigType | None:
        """Return the type registered under ``key``, or None."""
        return self._types.get(key)

    def __contains__(self, key: object) -> bool:
        """Return whether ``key`` is registered."""
        return key in self._types

    def __iter__(self) -> Iterator[ConfigType]:
        """Iterate over the types sorted by label, as the admin lists them."""
        return iter(sorted(self._types.values(), key=lambda config_type: config_type.label.lower()))


def build_registry(types_setting: Any, *, strict: bool = True) -> Registry:
    """Return a registry of the built-ins, the custom types in ``types_setting``, and their variants.

    :param types_setting: the value of ``DYNAMIC_CONFIGS["TYPES"]``
    :param strict: raise on an invalid setting or entry; when False, log each problem at ERROR and skip it, so the
        built-ins and every valid custom type keep working (configs of a skipped type read as unregistered)
    :rtype: Registry
    :raises TypeConfigError: the setting or one of its entries is invalid (only when ``strict``)
    """
    base = {config_type.key: config_type for config_type in BUILTIN_TYPES}
    if not isinstance(types_setting, Mapping):
        error = TypeConfigError("DYNAMIC_CONFIGS['TYPES'] must be a dict.", "dynamic_configs.E001")
        if strict:
            raise error
        _log_skipped(error)
        types_setting = {}
    for key, entry in types_setting.items():
        try:
            base[key] = load_custom_type(key, entry)
        except TypeConfigError as error:
            if strict:
                raise
            _log_skipped(error)
    types = list(base.values())
    for config_type in base.values():
        if config_type.listable:
            types.append(list_variant(config_type))
            if config_type.hashable:
                types.append(set_variant(config_type))
    return Registry(types)


def _log_skipped(error: TypeConfigError) -> None:
    """Log a custom-type problem that the non-strict build skipped."""
    log(
        logger,
        logging.ERROR,
        "Skipping invalid config type setting: %s [%s]; run manage.py check for details",
        error,
        error.check_id,
    )


_registry: Registry | None = None


def get_registry() -> Registry:
    """Return the registry, building it on first use."""
    # A lazily built module-level singleton, reset when DYNAMIC_CONFIGS changes.
    global _registry
    if _registry is None:
        # Not strict: a broken TYPES entry must not stop every config being read (system checks don't run under
        # gunicorn or uwsgi). The problem is logged and only configs of the broken type are affected.
        _registry = build_registry(get_settings()["TYPES"], strict=False)
        log(logger, logging.DEBUG, "Built the config type registry (%d types)", len(list(_registry)))
    return _registry


def reset_registry() -> None:
    """Forget the registry so the next ``get_registry`` rebuilds it."""
    global _registry
    _registry = None


@receiver(setting_changed)
def _reset_on_settings_change(*, setting: str, **kwargs: Any) -> None:
    """Rebuild the registry on next use when ``DYNAMIC_CONFIGS`` changes (for example under ``override_settings``)."""
    if setting == "DYNAMIC_CONFIGS":
        reset_registry()
