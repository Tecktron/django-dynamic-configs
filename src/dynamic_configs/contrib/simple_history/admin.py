"""The config admin with django-simple-history's History button."""

from __future__ import annotations

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

# Imported first, so its registration is there to replace whatever the order of INSTALLED_APPS.
import dynamic_configs.admin  # noqa: F401
from dynamic_configs.admin import ConfigAdminMixin
from dynamic_configs.conf import get_settings
from dynamic_configs.models import Config


class ConfigHistoryAdmin(ConfigAdminMixin, SimpleHistoryAdmin):
    """The config admin with a History page for each config, from which a past version can be restored."""


def register_history_admin(site: admin.AdminSite = admin.site) -> None:
    """Replace ``Config``'s admin on ``site`` with ``ConfigHistoryAdmin``, unless ``REGISTER_ADMIN`` is False.

    Calling it again does nothing.
    """
    if not get_settings()["REGISTER_ADMIN"]:
        return
    if site.is_registered(Config):
        if isinstance(site.get_model_admin(Config), ConfigHistoryAdmin):
            return
        site.unregister(Config)
    site.register(Config, ConfigHistoryAdmin)


register_history_admin()
