import pytest
from django.contrib import admin
from django.contrib.admin import AdminSite
from simple_history.admin import SimpleHistoryAdmin

import dynamic_configs
from dynamic_configs.admin import ConfigAdmin, register_admin
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
