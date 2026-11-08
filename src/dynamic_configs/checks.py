"""System checks for the ``DYNAMIC_CONFIGS`` setting, so mistakes show up in ``manage.py check`` at startup."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, register

from dynamic_configs.conf import DEFAULTS
from dynamic_configs.types.registry import TypeConfigError, load_custom_type


@register()
def check_settings(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Check ``DYNAMIC_CONFIGS``.

    Covers its shape, the cache alias, the timeout, ``REGISTER_ADMIN``, ``STRIP_STRINGS`` and every custom type.

    :returns: one error per problem found
    :rtype: list[CheckMessage]
    """
    project = getattr(settings, "DYNAMIC_CONFIGS", {})
    if not isinstance(project, Mapping):
        return [Error("DYNAMIC_CONFIGS must be a dict.", id="dynamic_configs.E001")]
    errors: list[CheckMessage] = [
        Error(
            f"DYNAMIC_CONFIGS has an unknown key {key!r}.",
            hint=f"Valid keys: {', '.join(DEFAULTS)}.",
            id="dynamic_configs.E001",
        )
        for key in project
        if key not in DEFAULTS
    ]
    errors += _check_cache(project.get("CACHE", DEFAULTS["CACHE"]))
    timeout = project.get("TIMEOUT", DEFAULTS["TIMEOUT"])
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 0):
        errors.append(
            Error(
                "DYNAMIC_CONFIGS['TIMEOUT'] must be a whole number of seconds (0 or more) or None.",
                id="dynamic_configs.E001",
            )
        )
    if not isinstance(project.get("REGISTER_ADMIN", DEFAULTS["REGISTER_ADMIN"]), bool):
        errors.append(Error("DYNAMIC_CONFIGS['REGISTER_ADMIN'] must be True or False.", id="dynamic_configs.E001"))
    strip = project.get("STRIP_STRINGS", DEFAULTS["STRIP_STRINGS"])
    # Tested by type: 1 and 0 would pass a membership test against (True, False, None).
    if strip is not None and not isinstance(strip, bool):
        errors.append(Error("DYNAMIC_CONFIGS['STRIP_STRINGS'] must be True, False or None.", id="dynamic_configs.E001"))
    errors += _check_types(project.get("TYPES", DEFAULTS["TYPES"]))
    return errors


def _check_cache(alias: Any) -> list[CheckMessage]:
    """Check that the cache alias is None or names a cache in ``CACHES``."""
    if alias is None:
        return []
    if not isinstance(alias, str):
        return [Error("DYNAMIC_CONFIGS['CACHE'] must be a cache alias or None.", id="dynamic_configs.E001")]
    if alias not in settings.CACHES:
        return [Error(f"DYNAMIC_CONFIGS['CACHE'] is {alias!r}, which isn't in CACHES.", id="dynamic_configs.E005")]
    return []


def _check_types(types: Any) -> list[CheckMessage]:
    """Check every custom type by loading it."""
    if not isinstance(types, Mapping):
        return [Error("DYNAMIC_CONFIGS['TYPES'] must be a dict.", id="dynamic_configs.E001")]
    errors: list[CheckMessage] = []
    for key, entry in types.items():
        try:
            load_custom_type(key, entry)
        except TypeConfigError as error:
            errors.append(Error(str(error), id=error.check_id))
    return errors
