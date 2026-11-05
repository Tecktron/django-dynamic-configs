"""Per-setting cache entries.

Each setting has one entry, ``dynamic_configs:v1:<name>``, holding ``(type_key, stored_text)``: the stored strings,
never a deserialized value, so custom classes are never pickled into the cache (a renamed class would break
unpickling). A setting known not to exist is cached as a marker, so ``get(name, default)`` doesn't query the database
every time. ``v1`` lets a later release change the format without reading old entries.

Cache failures are logged and never raised: callers fall back to the database.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Final

from django.core.cache import InvalidCacheBackendError, caches
from django.core.cache.backends.base import BaseCache
from django.core.cache.backends.dummy import DummyCache
from django.db import transaction

from dynamic_configs.conf import get_settings
from dynamic_configs.log import log

logger = logging.getLogger(__name__)

KEY_PREFIX: Final = "dynamic_configs:v1:"
_ABSENT_MARKER: Final = "dynamic_configs:absent"

Entry = tuple[str, "str | None"]


class _Sentinel:
    """A named marker value."""

    def __init__(self, name: str) -> None:
        """Name the marker (shown by ``repr``)."""
        self._name = name

    def __repr__(self) -> str:
        """Return the marker's name."""
        return self._name


NOT_CACHED: Final = _Sentinel("NOT_CACHED")
ABSENT: Final = _Sentinel("ABSENT")


def cache_key(name: str) -> str:
    """Return the cache key for the setting ``name``."""
    return f"{KEY_PREFIX}{name}"


def get_cache() -> BaseCache | None:
    """Return the configured cache, or None when caching is off.

    Caching is off when ``CACHE`` is None or isn't a configured alias (logged as a warning), or the backend is
    DummyCache.
    """
    alias = get_settings()["CACHE"]
    if alias is None:
        return None
    try:
        backend = caches[alias]
    except InvalidCacheBackendError:
        log(logger, logging.WARNING, "Cache alias %r isn't configured; reading configs without a cache", alias)
        return None
    return None if isinstance(backend, DummyCache) else backend


def read(name: str) -> Entry | _Sentinel:
    """Return the cached entry for ``name``, ``ABSENT`` if it's cached as missing, or ``NOT_CACHED``."""
    backend = get_cache()
    if backend is None:
        return NOT_CACHED
    try:
        raw = backend.get(cache_key(name))
    except Exception:
        log(
            logger,
            logging.WARNING,
            "Cache read failed for config %r; reading from the database",
            name,
            config_name=name,
            exc_info=True,
        )
        return NOT_CACHED
    if raw == _ABSENT_MARKER:
        log(logger, logging.DEBUG, "Cache hit for config %r: it doesn't exist", name, config_name=name)
        return ABSENT
    # A list too: caches that serialize to JSON or msgpack (django-redis's JSON serializer, say) give tuples back as
    # lists, and treating those as misses would send every read to the database.
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        log(logger, logging.DEBUG, "Cache hit for config %r", name, config_name=name)
        return (raw[0], raw[1])
    log(logger, logging.DEBUG, "Cache miss for config %r", name, config_name=name)
    return NOT_CACHED


def write(name: str, entry: Entry | _Sentinel, *, overwrite: bool = True) -> None:
    """Cache ``entry`` (a ``(type_key, text)`` tuple, or ``ABSENT``) for ``name``.

    :param name: the setting's name
    :param entry: what to cache
    :param overwrite: replace an existing entry (``set``); when False, only fill an empty slot (``add``), so a slow
        reader can't replace the newer entry a writer cached after committing
    """
    backend = get_cache()
    if backend is None:
        return
    value = _ABSENT_MARKER if entry is ABSENT else entry
    timeout = get_settings()["TIMEOUT"]
    try:
        if overwrite:
            backend.set(cache_key(name), value, timeout=timeout)
            stored = True
        else:
            stored = backend.add(cache_key(name), value, timeout=timeout)
    except Exception:
        log(
            logger,
            logging.WARNING,
            "Cache write failed for config %r; any old entry expires after the cache timeout",
            name,
            config_name=name,
            exc_info=True,
        )
        return
    if stored:
        log(logger, logging.DEBUG, "Cached config %r", name, config_name=name)
    else:
        log(logger, logging.DEBUG, "Config %r was already cached; kept that entry", name, config_name=name)


def write_on_commit(name: str, entry: Entry | _Sentinel, *, using: str, overwrite: bool) -> None:
    """Cache ``entry`` once the current transaction on ``using`` commits (at once outside a transaction).

    A value read inside a transaction may never be committed; caching it straight away would leave a rolled-back
    value in the cache for every process until it expired.
    """
    transaction.on_commit(partial(write, name, entry, overwrite=overwrite), using=using)


def delete(name: str) -> None:
    """Remove the cached entry for ``name``."""
    backend = get_cache()
    if backend is None:
        return
    try:
        backend.delete(cache_key(name))
    except Exception:
        log(
            logger,
            logging.WARNING,
            "Cache delete failed for config %r; any old entry expires after the cache timeout",
            name,
            config_name=name,
            exc_info=True,
        )
