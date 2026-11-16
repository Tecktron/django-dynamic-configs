"""System checks for the django-simple-history integration."""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.checks import CheckMessage, Error, register


@register()
def check_simple_history_installed(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Check that ``simple_history`` is in ``INSTALLED_APPS``, as the integration needs.

    :returns: an error when it isn't
    :rtype: list[CheckMessage]
    """
    if apps.is_installed("simple_history"):
        return []
    return [
        Error(
            'dynamic_configs.contrib.simple_history is installed, but "simple_history" isn\'t in INSTALLED_APPS.',
            hint='Add "simple_history" to INSTALLED_APPS.',
            id="dynamic_configs.E101",
        )
    ]


@register()
def check_history_ids(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Check that ``SIMPLE_HISTORY_HISTORY_ID_USE_UUID`` isn't set: the shipped migration creates integer ids.

    :returns: an error when it's set
    :rtype: list[CheckMessage]
    """
    if not getattr(settings, "SIMPLE_HISTORY_HISTORY_ID_USE_UUID", False):
        return []
    return [
        Error(
            "SIMPLE_HISTORY_HISTORY_ID_USE_UUID is set, but the config history's migration creates integer ids, so "
            "saving a config would fail.",
            hint="Remove SIMPLE_HISTORY_HISTORY_ID_USE_UUID; the simple-history integration doesn't support it.",
            id="dynamic_configs.E102",
        )
    ]
