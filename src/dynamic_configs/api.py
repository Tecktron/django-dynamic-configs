"""The public API for reading and writing configs; import it from the package (``import dynamic_configs``)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError

from dynamic_configs import _overrides, cache
from dynamic_configs.cache import Entry
from dynamic_configs.exceptions import ConfigValueError
from dynamic_configs.log import log
from dynamic_configs.models import NAME_REGEX, Config, ConfigDoesNotExist
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
            cache.write(name, entry)
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
