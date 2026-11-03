import pytest
from django.contrib import admin
from django.contrib.admin import AdminSite

from dynamic_configs.admin import ConfigAdmin, register_admin
from dynamic_configs.models import Config

pytestmark = pytest.mark.django_db

URL = "/admin/dynamic_configs/config/"


def change_url(name):
    return f"{URL}{name}/change/"


def make(name="SITE_NAME", type_key="str", value="Example", **fields):
    return Config.objects.create(name=name, type=type_key, value=value, **fields)


def test_configs_are_registered_with_the_admin():
    assert admin.site.is_registered(Config)


def test_register_admin_respects_the_setting_and_is_idempotent(settings):
    site = AdminSite()
    settings.DYNAMIC_CONFIGS = {"REGISTER_ADMIN": False}
    register_admin(site)
    assert not site.is_registered(Config)
    settings.DYNAMIC_CONFIGS = {}
    register_admin(site)
    register_admin(site)
    assert isinstance(site.get_model_admin(Config), ConfigAdmin)


def test_the_list_shows_type_labels_and_value_previews(admin_client):
    make()
    make("HOSTS", "list:str", '["a.example", "b.example"]')
    make("NOTE", "str", None, allow_null=True)
    make("THEME", "gone", "dark")
    make("BROKEN", "list:str", "not json")
    make("LONG", "text", "x" * 200)
    content = admin_client.get(URL).content.decode()
    assert "List of String" in content
    assert "a.example, b.example" in content
    assert "gone (not registered)" in content
    assert "not json" in content
    assert "x" * 79 + "…" in content


def test_the_add_page_offers_every_type(admin_client):
    content = admin_client.get(f"{URL}add/").content.decode()
    assert "List of Integer" in content
    assert "vLargeTextField" in content


def test_adding_saves_and_redirects(admin_client):
    response = admin_client.post(
        f"{URL}add/", {"name": "PORTS", "type": "list:int", "value": "80\n443", "description": "", "_save": "Save"}
    )
    assert response.status_code == 302
    assert Config.objects.get(name="PORTS").value == '["80", "443"]'


def test_adding_shows_line_errors(admin_client):
    response = admin_client.post(
        f"{URL}add/", {"name": "PORTS", "type": "list:int", "value": "80\nhttp", "description": "", "_save": "Save"}
    )
    assert response.status_code == 200
    assert "Line 2: Enter a whole number" in response.content.decode()


def test_the_change_page_shows_name_and_type_read_only(admin_client):
    make("MAX_RETRIES", "int", "3")
    content = admin_client.get(change_url("MAX_RETRIES")).content.decode()
    assert 'name="name"' not in content
    assert 'name="type"' not in content
    assert 'name="value" value="3"' in content


def test_dates_and_texts_use_the_admin_widgets(admin_client):
    make("LAUNCH", "date", "2026-11-02")
    make("NOTES", "text", "line one\nline two")
    assert "vDateField" in admin_client.get(change_url("LAUNCH")).content.decode()
    assert "vLargeTextField" in admin_client.get(change_url("NOTES")).content.decode()


def test_datetimes_are_entered_in_local_time_and_stored_in_utc(admin_client):
    # Review focus: the admin works in the site's time zone; storage is UTC.
    make("STARTS_AT", "datetime", "2026-11-02T22:00:00+00:00")
    content = admin_client.get(change_url("STARTS_AT")).content.decode()
    assert 'name="value_0"' in content
    assert 'value="17:00:00"' in content
    response = admin_client.post(
        change_url("STARTS_AT"), {"value_0": "2026-11-03", "value_1": "09:30", "description": "", "_save": "Save"}
    )
    assert response.status_code == 302
    assert Config.objects.get(name="STARTS_AT").value == "2026-11-03T14:30:00+00:00"


def test_booleans_that_allow_null_get_a_three_way_choice(admin_client):
    make("BETA", "bool", None, allow_null=True)
    content = admin_client.get(change_url("BETA")).content.decode()
    assert '<select name="value"' in content
    assert "Unknown" in content


def test_an_unregistered_type_is_read_only_with_a_warning(admin_client):
    make("THEME", "gone", "dark")
    content = admin_client.get(change_url("THEME")).content.decode()
    assert "isn&#x27;t registered" in content
    assert 'name="value"' not in content
    assert "dark" in content


def test_a_missing_config_redirects(admin_client):
    assert admin_client.get(change_url("MISSING")).status_code == 302


def test_a_types_own_widget_is_kept(admin_client, settings):
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {
            "color": {
                "type": "tests.custom_types.Color",
                "serializer": "tests.custom_types.ColorSerializer",
                "form": "tests.custom_types.CodeEditorColorField",
            }
        }
    }
    make("BRAND", "color", "#1a2b3c")
    assert 'class="code-editor"' in admin_client.get(change_url("BRAND")).content.decode()
