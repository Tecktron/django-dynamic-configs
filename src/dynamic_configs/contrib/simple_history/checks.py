"""System check for the django-simple-history integration."""

from __future__ import annotations

from typing import Any

from django.apps import apps
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
