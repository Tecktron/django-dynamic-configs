"""A project's own history admin, combined in the documented order, on its own admin site."""

from django.contrib.admin import AdminSite
from django.urls import path
from simple_history.admin import SimpleHistoryAdmin

from dynamic_configs.admin import ConfigAdminMixin
from dynamic_configs.models import Config


class ProjectConfigAdmin(ConfigAdminMixin, SimpleHistoryAdmin):
    """The config admin a project registers itself."""


site = AdminSite(name="project_admin")
site.register(Config, ProjectConfigAdmin)

urlpatterns = [path("admin/", site.urls)]
