"""The package's settings: ``settings.DYNAMIC_CONFIGS`` with defaults applied."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

DEFAULTS: dict[str, Any] = {
    "CACHE": "default",
    "TIMEOUT": 300,
    "TYPES": {},
    "REGISTER_ADMIN": True,
}


@functools.cache
def get_settings() -> Mapping[str, Any]:
    """Return ``DYNAMIC_CONFIGS`` merged over the defaults.

    A value that isn't a dict is ignored here (the system checks report it), so a mistake in settings can't stop
    configs being read.

    :returns: a read-only mapping with every key in ``DEFAULTS``
    :rtype: Mapping[str, Any]
    """
    project = getattr(settings, "DYNAMIC_CONFIGS", {})
    merged = dict(DEFAULTS)
    if isinstance(project, Mapping):
        merged.update(project)
    return MappingProxyType(merged)


@receiver(setting_changed)
def _reset_settings(*, setting: str, **kwargs: Any) -> None:
    """Forget the cached settings when ``DYNAMIC_CONFIGS`` changes (for example under ``override_settings``)."""
    if setting == "DYNAMIC_CONFIGS":
        get_settings.cache_clear()
