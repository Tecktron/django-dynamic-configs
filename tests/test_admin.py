import html
import re

import pytest
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.staticfiles import finders

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


@pytest.mark.parametrize(
    "stored",
    [
        '"abc"',  # a JSON string, which joining would split into letters
        "[1, 2]",  # not strings
        "[" * 100_000 + "]" * 100_000,  # nested too deeply for Python's reader
    ],
)
def test_a_list_that_isnt_an_array_of_strings_previews_as_stored(admin_client, stored):
    # Only a hand-edited row can hold these.
    make("ODD", "list:str", stored)
    response = admin_client.get(URL)
    assert response.status_code == 200
    assert html.escape(stored[:79]) in response.content.decode()


def test_the_add_page_starts_with_the_type(admin_client):
    content = admin_client.get(f"{URL}add/").content.decode()
    assert "List of Integer" in content
    assert 'name="name"' not in content
    assert 'name="value"' not in content
    assert 'name="_save"' in content
    assert 'name="_addanother"' not in content
    assert 'name="_continue"' not in content
    assert "data-dynamic-configs-type" in content
    assert "dynamic_configs/admin.js" in content


def test_choosing_a_type_moves_to_its_value(admin_client):
    response = admin_client.post(f"{URL}add/", {"type": "list:int", "_save": "Save"})
    assert response.status_code == 302
    assert response["Location"] == f"{URL}add/?type=list%3Aint"


def test_choosing_a_type_keeps_the_pages_query(admin_client):
    # Review focus: a popup add must stay a popup through the redirect.
    response = admin_client.post(f"{URL}add/?_popup=1", {"type": "int", "_save": "Save"})
    assert response["Location"] == f"{URL}add/?_popup=1&type=int"


def test_choosing_no_type_is_an_error(admin_client):
    response = admin_client.post(f"{URL}add/", {"type": "", "_save": "Save"})
    assert response.status_code == 200
    assert "This field is required." in response.content.decode()


def test_an_unknown_type_in_the_address_starts_again(admin_client):
    # Review focus: a stale or hand-edited ?type= gives the first step, not a server error.
    content = admin_client.get(f"{URL}add/?type=gone").content.decode()
    assert "data-dynamic-configs-type" in content
    assert 'name="value"' not in content


def test_the_value_step_shows_the_type_and_its_field(admin_client):
    content = admin_client.get(f"{URL}add/?type=date").content.decode()
    assert 'name="name"' in content
    assert 'name="type"' not in content
    assert '<div class="readonly">date</div>' in content
    assert "vDateField" in content
    assert 'name="_addanother"' in content


def test_adding_saves_and_redirects(admin_client):
    response = admin_client.post(
        f"{URL}add/?type=list:int", {"name": "PORTS", "value": "80\n443", "description": "", "_save": "Save"}
    )
    assert response.status_code == 302
    config = Config.objects.get(name="PORTS")
    assert (config.type, config.value) == ("list:int", '["80", "443"]')


def test_adding_from_a_searched_list_saves(admin_client):
    # Review: from a searched, filtered or sorted list, Django points the form at ?_changelist_filters=..., which
    # dropped type= and sent the save back to the first step.
    page = f"{URL}add/?_changelist_filters=q%3DSITE&type=int"
    content = admin_client.get(page).content.decode()
    action = html.unescape(re.search(r'<form action="([^"]*)"[^>]* id="config_form"', content).group(1))
    data = {"name": "MAX_RETRIES", "value": "3", "description": "", "_save": "Save"}
    response = admin_client.post(f"{URL}add/{action}", data)
    assert response.status_code == 302
    assert Config.objects.get(name="MAX_RETRIES").value == "3"
    assert response["Location"] == f"{URL}?q=SITE"


def test_adding_shows_line_errors(admin_client):
    response = admin_client.post(
        f"{URL}add/?type=list:int", {"name": "PORTS", "value": "80\nhttp", "description": "", "_save": "Save"}
    )
    assert response.status_code == 200
    assert "Line 2: Enter a whole number" in response.content.decode()


def test_the_admin_script_is_shipped():
    # Under tox the suite runs against the built wheel, so this also checks the script is packaged.
    assert finders.find("dynamic_configs/admin.js") is not None


@pytest.mark.parametrize(
    "path", ["dynamic_configs/json_editor.js", "dynamic_configs/list_editor.js", "dynamic_configs/admin.css"]
)
def test_the_editors_files_are_shipped(path):
    # The stylesheet needs its own package-data pattern, which this catches under tox.
    assert finders.find(path) is not None


def test_json_nested_too_deeply_is_a_form_error(admin_client):
    # Review: the editor accepts any depth, and saving one Python couldn't read was a server error.
    depth = 100_000
    data = {"name": "DEEP", "value": "[" * depth + "]" * depth, "description": "", "_save": "Save"}
    response = admin_client.post(f"{URL}add/?type=json", data)
    assert response.status_code == 200
    assert "The JSON is nested too deeply." in response.content.decode()


@pytest.mark.parametrize("view", ["change", "add"])
def test_json_values_get_the_editor_in_the_admin(admin_client, view):
    make("FLAGS", "json", '{"beta": true}')
    url = change_url("FLAGS") if view == "change" else f"{URL}add/?type=json"
    content = admin_client.get(url).content.decode()
    assert "vLargeTextField" in content
    assert "data-dynamic-configs-json" in content
    assert "dynamic_configs/json_editor.js" in content
    assert "dynamic_configs/admin.css" in content


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


def post_datetime(admin_client, name, day, clock, zone):
    data = {"value_0": day, "value_1": clock, "value_2": zone, "description": "", "_save": "Save"}
    return admin_client.post(change_url(name), data)


def test_datetimes_are_shown_in_the_current_zone_and_stored_in_utc(admin_client):
    # Review focus: the admin works in the site's time zone; storage is UTC.
    make("STARTS_AT", "datetime", "2026-11-02T22:00:00+00:00")
    content = admin_client.get(change_url("STARTS_AT")).content.decode()
    assert 'value="2026-11-02"' in content
    assert 'value="17:00:00"' in content
    assert '<option value="America/New_York" selected>' in content
    response = post_datetime(admin_client, "STARTS_AT", "2026-11-03", "09:30", "America/New_York")
    assert response.status_code == 302
    assert Config.objects.get(name="STARTS_AT").value == "2026-11-03T14:30:00+00:00"


def test_a_datetime_can_be_entered_in_another_zone(admin_client):
    make("STARTS_AT", "datetime", "2026-11-02T22:00:00+00:00")
    assert post_datetime(admin_client, "STARTS_AT", "2026-11-03", "09:30", "Asia/Tokyo").status_code == 302
    assert Config.objects.get(name="STARTS_AT").value == "2026-11-03T00:30:00+00:00"


def test_saving_a_datetime_as_shown_keeps_its_instant(admin_client):
    # Review focus: showing a UTC value in local time and saving it back must not move it.
    make("STARTS_AT", "datetime", "2026-07-01T03:15:00+00:00")
    content = admin_client.get(change_url("STARTS_AT")).content.decode()
    assert 'value="2026-06-30"' in content
    assert 'value="23:15:00"' in content
    post_datetime(admin_client, "STARTS_AT", "2026-06-30", "23:15:00", "America/New_York")
    assert Config.objects.get(name="STARTS_AT").value == "2026-07-01T03:15:00+00:00"


def test_a_datetime_at_the_start_of_the_calendar_opens(admin_client):
    # Review: in New York, 0001-01-01 00:00 UTC would be before year 1, which was a server error.
    make("STARTS_AT", "datetime", "0001-01-01T00:00:00+00:00")
    content = admin_client.get(change_url("STARTS_AT")).content.decode()
    assert 'value="0001-01-01"' in content
    assert '<option value="UTC" selected>' in content


def test_a_time_skipped_by_daylight_saving_is_a_form_error(admin_client):
    make("STARTS_AT", "datetime", "2026-11-02T22:00:00+00:00")
    response = post_datetime(admin_client, "STARTS_AT", "2026-03-08", "02:30", "America/New_York")
    assert response.status_code == 200
    assert "couldn&#x27;t be interpreted in time zone America/New_York" in response.content.decode()


def test_the_datetime_picker_uses_the_admin_widgets_and_script(admin_client):
    make("STARTS_AT", "datetime", None, allow_null=True)
    content = admin_client.get(change_url("STARTS_AT")).content.decode()
    assert "vDateField" in content
    assert "vTimeField" in content
    assert "data-dynamic-configs-zone" in content
    assert "dynamic_configs/admin.js" in content
    assert "A date, a time and the time zone they're in." in content
    assert "YYYY-MM-DD HH:MM" not in content
    assert "server's time zone" not in content


def test_the_add_page_has_the_datetime_picker(admin_client):
    assert 'name="value_2"' in admin_client.get(f"{URL}add/?type=datetime").content.decode()


def test_with_use_tz_off_the_admin_says_which_zone_times_are_in(admin_client, settings):
    settings.USE_TZ = False
    make("STARTS_AT", "datetime", "2026-11-02T17:00:00")
    content = admin_client.get(change_url("STARTS_AT")).content.decode()
    assert "A date and a time. Times are in the server's time zone (America/New_York)." in content
    assert 'name="value_2"' not in content
    assert 'value="17:00:00"' in content


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
