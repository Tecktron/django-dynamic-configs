"""A project's own history admins, combined in the documented order, on admin sites of their own."""

from django.contrib.admin import AdminSite
from django.urls import path
from simple_history.admin import SimpleHistoryAdmin

from dynamic_configs.admin import ConfigAdminMixin
from dynamic_configs.models import Config


class ProjectConfigAdmin(ConfigAdminMixin, SimpleHistoryAdmin):
    """The config admin a project registers itself."""


class NoRevertConfigAdmin(ProjectConfigAdmin):
    """A project's admin that disables reverting for everyone."""

    def revert_disabled(self, request, obj=None):
        """Disable reverting."""
        return True


site = AdminSite(name="project_admin")
site.register(Config, ProjectConfigAdmin)
no_revert_site = AdminSite(name="no_revert_admin")
no_revert_site.register(Config, NoRevertConfigAdmin)

urlpatterns = [path("admin/", site.urls), path("no-revert-admin/", no_revert_site.urls)]
