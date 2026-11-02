"""The public API for reading and writing configs; import it from the package (``import dynamic_configs``)."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import DatabaseError, router, transaction

from dynamic_configs import _overrides, cache
from dynamic_configs.cache import Entry
from dynamic_configs.exceptions import ConfigTypeError, ConfigValueError
from dynamic_configs.log import log
from dynamic_configs.models import NAME_REGEX, Config, ConfigDoesNotExist
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.registry import get_registry

logger = logging.getLogger(__name__)

# Distinguishes "no default passed" from default=None.
_NO_DEFAULT: Any = object()


def get(name: str, default: Any = _NO_DEFAULT, *, no_cache: bool = False) -> Any:
    """Return the value of the config ``name``.

    Reads overrides (from the test helpers) first, then the cache, then the database. If you pass a default, this
    never raises: a missing setting, a database error or an unreadable value all return the default (the last two are
    logged).

    :param name: the config's name, such as ``"SITE_NAME"``
    :param default: returned when the config doesn't exist or can't be read
    :param no_cache: skip the cache read (the cache entry is still refreshed with what's read)
    :returns: the typed value, or None for an empty ``allow_null`` config
    :raises ConfigDoesNotExist: the config doesn't exist and no default was passed
    :raises ConfigValueError: the stored value can't be read (or its type isn't registered) and no default was passed
    :raises DatabaseError: the database can't be reached and no default was passed
    """
    found, override = _overrides.lookup(name)
    if found:
        return override
    has_default = default is not _NO_DEFAULT
    if not (isinstance(name, str) and NAME_REGEX.search(name)):
        # A name that doesn't match the pattern can never be saved, so there's nothing to cache or query.
        entry: Entry | object = cache.ABSENT
    else:
        entry = cache.NOT_CACHED if no_cache else cache.read(name)
        if entry is cache.NOT_CACHED:
            try:
                entry = _load_entry(name)
            except DatabaseError:
                if not has_default:
                    raise
                log(
                    logger,
                    logging.WARNING,
                    "Database read failed for config %r; returning the default",
                    name,
                    config_name=name,
                    exc_info=True,
                )
                return default
            # Cached only once the read's transaction commits; a plain read only fills an empty slot, while
            # no_cache=True refreshes whatever is there.
            cache.write_on_commit(name, entry, using=router.db_for_read(Config), overwrite=no_cache)
    if entry is cache.ABSENT:
        if not has_default:
            raise ConfigDoesNotExist(f"Config {name!r} does not exist.")
        return default
    type_key, text = entry  # type: ignore[misc]
    try:
        return _decode(name, type_key, text)
    except ConfigValueError:
        if not has_default:
            raise
        log(
            logger,
            logging.ERROR,
            "Config %r can't be read (type %r); returning the default",
            name,
            type_key,
            config_name=name,
            config_type=type_key,
            exc_info=True,
        )
        return default


def _load_entry(name: str) -> Entry | object:
    """Read ``(type_key, text)`` for ``name`` from the database, or ``cache.ABSENT`` if there's no such row."""
    row = Config.objects.filter(name=name).values_list("type", "value").first()
    log(logger, logging.DEBUG, "Read config %r from the database", name, config_name=name)
    return cache.ABSENT if row is None else (row[0], row[1])


def _unregistered(name: str, type_key: str) -> ConfigValueError:
    """Return the error for a config whose stored type isn't in the registry."""
    return ConfigValueError(
        f"Config {name!r} has type {type_key!r}, which isn't registered; add it to DYNAMIC_CONFIGS['TYPES']."
    )


def _decode(name: str, type_key: str, text: str | None) -> Any:
    """Return the value stored as ``text`` for a config of type ``type_key``; None stays None."""
    if text is None:
        return None
    config_type = get_registry().get(type_key)
    if config_type is None:
        raise _unregistered(name, type_key)
    try:
        return config_type.from_text(text)
    except ConfigValueError as error:
        raise ConfigValueError(f"Config {name!r} can't be read: {error}") from error


def get_or_create(
    name: str, type: str, value: Any, *, description: str = "", allow_null: bool = False
) -> tuple[Any, bool]:
    """Return the config ``name``, creating it with ``value`` if it doesn't exist.

    Always reads the database (then refreshes the cache), so code that declares its settings this way sees what an
    admin has changed.

    :param name: the config's name (UPPER_SNAKE_CASE)
    :param type: a registered type key, such as ``"int"`` or ``"list:str"``
    :param value: the value to create it with (None needs ``allow_null=True``)
    :param description: notes for admins, used only when creating
    :param allow_null: whether the config may be empty (None), used only when creating
    :returns: ``(value, created)``; the stored value when it already existed, else the created value as ``get`` will
        return it (for example a naive datetime comes back in UTC)
    :rtype: tuple[Any, bool]
    :raises ConfigTypeError: the type isn't registered, the value has the wrong type, None isn't allowed, or the
        config exists with another type
    :raises ConfigValueError: the name is invalid or the serializer rejects the value
    """
    found, override = _overrides.lookup(name)
    if found:
        return override, False
    try:
        config = Config.objects.get(name=name)
        created = False
    except Config.DoesNotExist:
        config, created = _create(name, type, value, description=description, allow_null=allow_null)
    if not created:
        if config.type != type:
            raise ConfigTypeError(f"Config {name!r} already exists with type {config.type!r}, not {type!r}.")
        cache.write_on_commit(name, (config.type, config.value), using=config._state.db, overwrite=True)
    return _decode(name, config.type, config.value), created


def _create(name: str, type_key: str, value: Any, *, description: str, allow_null: bool) -> tuple[Config, bool]:
    """Validate and create the config; ``created`` is False if another process created it first."""
    _validate_name(name)
    text = _to_text(name, _require_type(type_key), value, allow_null=allow_null)
    config, created = Config.objects.get_or_create(
        name=name,
        defaults={"type": type_key, "value": text, "allow_null": allow_null, "description": description},
    )
    if created:
        log(logger, logging.INFO, "Created config %r (type %r)", name, type_key, config_name=name, config_type=type_key)
    return config, created


def update(name: str, new_value: Any, *, allow_null: bool | None = None) -> None:
    """Change the value of the existing config ``name``.

    :param name: the config's name
    :param new_value: the new value (None needs the config, after this call, to allow None)
    :param allow_null: None keeps the config's flag; True or False updates it in the same save
    :raises ConfigDoesNotExist: the config doesn't exist
    :raises ConfigTypeError: the value has the wrong type, or is None when None isn't allowed
    :raises ConfigValueError: the serializer rejects the value, or the config's type isn't registered
    """
    with transaction.atomic():
        try:
            config = Config.objects.select_for_update().get(name=name)
        except Config.DoesNotExist:
            raise ConfigDoesNotExist(f"Config {name!r} does not exist.") from None
        config_type = get_registry().get(config.type)
        if config_type is None:
            raise _unregistered(name, config.type)
        flag = config.allow_null if allow_null is None else allow_null
        config.value = _to_text(name, config_type, new_value, allow_null=flag)
        config.allow_null = flag
        config.save(update_fields=["value", "allow_null", "modified_on"])
    log(logger, logging.INFO, "Updated config %r", name, config_name=name, config_type=config.type)


def delete(name: str) -> bool:
    """Delete the config ``name``.

    :param name: the config's name
    :returns: True if it was deleted, False if it didn't exist
    :rtype: bool
    """
    # QuerySet.delete() sends post_delete for each row (a receiver is connected), so the cache is updated.
    deleted, _ = Config.objects.filter(name=name).delete()
    if deleted:
        log(logger, logging.INFO, "Deleted config %r", name, config_name=name)
    return deleted > 0


def _validate_name(name: Any) -> None:
    """Raise ConfigValueError unless ``name`` is a valid config name."""
    if not isinstance(name, str):
        raise ConfigValueError(f"Config names must be strings, not {type(name).__name__}.")
    try:
        Config._meta.get_field("name").run_validators(name)
    except ValidationError as error:
        raise ConfigValueError(f"Invalid config name {name!r}: {' '.join(error.messages)}") from error


def _require_type(type_key: str) -> ConfigType:
    """Return the registered type ``type_key``, or raise ConfigTypeError."""
    config_type = get_registry().get(type_key)
    if config_type is None:
        raise ConfigTypeError(f"{type_key!r} isn't a registered config type.")
    return config_type


def _to_text(name: str, config_type: ConfigType, value: Any, *, allow_null: bool) -> str | None:
    """Return the text to store for ``value``; None only when ``allow_null``."""
    if value is None:
        if not allow_null:
            raise ConfigTypeError(f"Config {name!r} doesn't allow None; pass allow_null=True to allow it.")
        return None
    return config_type.to_text(value)


async def aget(name: str, default: Any = _NO_DEFAULT, *, no_cache: bool = False) -> Any:
    """Run :func:`get` without blocking the event loop; same parameters, return value and errors."""
    return await sync_to_async(get)(name, default, no_cache=no_cache)


async def aget_or_create(
    name: str, type: str, value: Any, *, description: str = "", allow_null: bool = False
) -> tuple[Any, bool]:
    """Run :func:`get_or_create` without blocking the event loop; same parameters, return value and errors."""
    return await sync_to_async(get_or_create)(name, type, value, description=description, allow_null=allow_null)


async def aupdate(name: str, new_value: Any, *, allow_null: bool | None = None) -> None:
    """Run :func:`update` without blocking the event loop; same parameters and errors."""
    await sync_to_async(update)(name, new_value, allow_null=allow_null)


async def adelete(name: str) -> bool:
    """Run :func:`delete` without blocking the event loop; same parameter and return value."""
    return await sync_to_async(delete)(name)
