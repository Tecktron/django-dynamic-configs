import pytest
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.core import checks
from simple_history.admin import SimpleHistoryAdmin

import dynamic_configs
from dynamic_configs.admin import ConfigAdmin, ConfigAdminMixin, register_admin
from dynamic_configs.contrib.simple_history.admin import ConfigHistoryAdmin, register_history_admin
from dynamic_configs.models import Config

pytestmark = pytest.mark.django_db

URL = "/admin/dynamic_configs/config/"


def change_url(name):
    return f"{URL}{name}/change/"


def test_the_admin_has_history():
    model_admin = admin.site.get_model_admin(Config)
    assert isinstance(model_admin, ConfigHistoryAdmin)
    assert isinstance(model_admin, SimpleHistoryAdmin)


def test_the_history_admin_passes_its_checks():
    # ConfigAdminMixin's W001 must not fire for simple_history's own options.
    assert ConfigHistoryAdmin(Config, AdminSite()).check() == []


@pytest.mark.parametrize(
    "bases",
    [(ConfigAdminMixin, SimpleHistoryAdmin), (ConfigAdminMixin, SimpleHistoryAdmin, admin.ModelAdmin)],
    ids=["mixin, SimpleHistoryAdmin", "mixin, SimpleHistoryAdmin, skin"],
)
def test_the_documented_order_passes_its_checks(bases):
    assert type("ProjectConfigAdmin", bases, {})(Config, AdminSite()).check() == []


def test_a_subclass_that_overrides_the_revert_view_passes_its_checks():
    # Its override runs first and reaches the mixin's through super(), so it isn't reported.
    class OwnRevertAdmin(ConfigHistoryAdmin):
        def history_form_view(self, request, object_id, version_id, extra_context=None):
            return super().history_form_view(request, object_id, version_id, extra_context)

    assert OwnRevertAdmin(Config, AdminSite()).check() == []


def test_a_base_before_the_mixin_that_overrides_its_history_view_is_an_error():
    reversed_admin = type("ReversedConfigAdmin", (SimpleHistoryAdmin, ConfigAdminMixin, admin.ModelAdmin), {})
    [error] = reversed_admin(Config, AdminSite()).check()
    assert (error.id, error.level, error.obj) == ("dynamic_configs.E006", checks.ERROR, reversed_admin)
    assert error.msg == (
        "ReversedConfigAdmin puts SimpleHistoryAdmin before ConfigAdminMixin, so its history_form_view runs instead "
        "of ConfigAdminMixin's."
    )
    assert error.hint == (
        "Put ConfigAdminMixin first among the base classes, as in "
        "class ConfigAdmin(ConfigAdminMixin, SimpleHistoryAdmin, ModelAdmin)."
    )


def test_admin_changes_record_who_made_them(admin_client, admin_user):
    dynamic_configs.get_or_create("SITE_NAME", "str", "Example")
    admin_client.post(change_url("SITE_NAME"), {"value": "Renamed", "allow_null": "", "description": ""})
    assert Config.history.filter(name="SITE_NAME").latest("history_date").history_user == admin_user


def test_a_past_version_of_a_list_opens_and_reverts(admin_client):
    dynamic_configs.get_or_create("HOSTS", "list:str", ["a.example"])
    dynamic_configs.update("HOSTS", ["b.example"])
    first = Config.history.filter(name="HOSTS").earliest("history_date")
    url = f"{URL}HOSTS/history/{first.history_id}/"
    response = admin_client.get(url)
    assert response.status_code == 200
    assert "data-dynamic-configs-list" in response.content.decode()
    admin_client.post(url, {"value": "a.example", "value__mode": "raw", "allow_null": "", "description": ""})
    assert Config.objects.get(name="HOSTS").value == '["a.example"]'


def test_register_history_admin_respects_the_setting_and_is_idempotent(settings):
    site = AdminSite()
    register_admin(site)
    settings.DYNAMIC_CONFIGS = {"REGISTER_ADMIN": False}
    register_history_admin(site)
    assert type(site.get_model_admin(Config)) is ConfigAdmin
    settings.DYNAMIC_CONFIGS = {}
    register_history_admin(site)
    register_history_admin(site)
    assert type(site.get_model_admin(Config)) is ConfigHistoryAdmin


def test_register_history_admin_registers_on_a_site_with_nothing_registered():
    site = AdminSite()
    register_history_admin(site)
    assert type(site.get_model_admin(Config)) is ConfigHistoryAdmin
