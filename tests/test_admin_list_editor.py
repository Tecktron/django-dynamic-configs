"""The admin's list editor on the server: its widget, its check URL, and saving."""

import json
import re
from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.contrib.auth.models import Permission
from django.test import Client

from dynamic_configs.forms.list import StoredTexts
from dynamic_configs.models import Config
from dynamic_configs.types.registry import get_registry

pytestmark = pytest.mark.django_db

URL = "/admin/dynamic_configs/config/"
COLOR = {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}


def change_url(name):
    return f"{URL}{name}/change/"


def ask(client, type_key, action, **fields):
    return client.post(f"{URL}list-item/{type_key}/", {"action": action, "name": "value__item", **fields})


def answer(client, type_key, action, **fields):
    response = ask(client, type_key, action, **fields)
    assert response.status_code == 200
    return response.json()


# ---- The widget ----


def test_list_values_get_the_list_editor(admin_client):
    content = admin_client.get(f"{URL}add/?type=list:int").content.decode()
    assert "data-dynamic-configs-list" in content
    assert 'data-check-url="/admin/dynamic_configs/config/list-item/list:int/"' in content
    assert 'data-set="false" data-sortable="true"' in content
    assert 'name="value__item"' in content
    assert 'name="value__mode" value="raw"' in content
    assert "dynamic_configs/list_editor.js" in content
    assert "dynamic_configs/admin.css" in content


def test_sets_and_unsortable_types_say_so(admin_client, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"color": COLOR}}
    assert 'data-set="true" data-sortable="false"' in admin_client.get(f"{URL}add/?type=set:int").content.decode()
    assert 'data-set="false" data-sortable="false"' in admin_client.get(f"{URL}add/?type=list:color").content.decode()


def test_the_item_editor_brings_its_widgets_scripts(admin_client):
    content = admin_client.get(f"{URL}add/?type=list:date").content.decode()
    assert 'name="value__item"' in content
    assert "vDateField" in content
    assert "admin/js/admin/DateTimeShortcuts.js" in content


# ---- The check URL ----


def test_check_returns_the_items_stored_text(admin_client):
    assert answer(admin_client, "list:int", "check", value__item="07", items="[]", position="") == {"text": "7"}


def test_check_returns_the_types_own_error(admin_client):
    assert answer(admin_client, "list:int", "check", value__item="a", items="[]") == {
        "errors": ["Enter a whole number."]
    }


def test_check_refuses_a_repeat_in_a_set_but_not_the_item_being_updated(admin_client):
    data = {"value__item": "1", "items": '["1", "2"]'}
    assert answer(admin_client, "set:int", "check", position="", **data) == {"errors": ["That's already in the set."]}
    assert answer(admin_client, "set:int", "check", position="0", **data) == {"text": "1"}


def test_load_returns_each_inputs_value(admin_client):
    text = get_registry().get("datetime").to_text(datetime(2026, 11, 2, 22, tzinfo=dt_timezone.utc))
    assert answer(admin_client, "list:datetime", "load", text=text) == {
        "values": {"value__item_0": "2026-11-02", "value__item_1": "17:00:00", "value__item_2": "America/New_York"}
    }
    assert answer(admin_client, "list:bool", "load", text="true") == {"values": {"value__item": True}}


def test_load_of_an_unreadable_item_is_an_error(admin_client):
    assert answer(admin_client, "list:int", "load", text="x") == {"errors": ["Enter a whole number, such as 42."]}


def test_lines_return_stored_texts_or_line_errors(admin_client):
    assert answer(admin_client, "list:int", "lines", lines='["1", " 02 "]') == {"texts": ["1", "2"]}
    assert answer(admin_client, "list:int", "lines", lines='["1", "x"]') == {
        "errors": ["Line 2: Enter a whole number, such as 42."]
    }


def test_lines_are_checked_as_saving_checks_them(admin_client):
    assert answer(admin_client, "list:str", "lines", lines=json.dumps(["a\x00b"])) == {
        "errors": ["Line 1: Null characters are not allowed."]
    }


def test_sort_orders_by_value_either_way(admin_client):
    items = '["10", "9", "100"]'
    assert answer(admin_client, "list:int", "sort", items=items, direction="ascending") == {"texts": ["9", "10", "100"]}
    assert answer(admin_client, "list:int", "sort", items=items, direction="descending") == {
        "texts": ["100", "10", "9"]
    }


def test_a_failing_sort_key_leaves_the_list_alone(admin_client, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"color": {**COLOR, "sort_key": "tests.custom_types.failing_key"}}}
    assert answer(admin_client, "list:color", "sort", items='["#bbbbbb", "#aaaaaa"]', direction="ascending") == {
        "errors": ["These items can't be sorted."]
    }


@pytest.mark.parametrize("items", ["not json", '{"a": 1}', '["a", 2]', "[" * 100000 + "]" * 100000])
def test_a_request_that_cant_be_read_is_an_error(admin_client, items):
    assert answer(admin_client, "list:int", "sort", items=items, direction="ascending") == {
        "errors": ["The request couldn't be read. Reload the page and try again."]
    }


@pytest.mark.parametrize("position", ["²", "9" * 5000, "-1", "x", "1" * 10])
def test_a_position_that_cant_be_read_is_an_error(admin_client, position):
    assert answer(admin_client, "list:int", "check", value__item="7", items="[]", position=position) == {
        "errors": ["The request couldn't be read. Reload the page and try again."]
    }


def test_an_unknown_action_is_a_bad_request(admin_client):
    assert ask(admin_client, "list:int", "save").status_code == 400


@pytest.mark.parametrize("type_key", ["gone", "int", "list:gone"])
def test_only_list_and_set_types_have_a_check_url(admin_client, type_key):
    assert ask(admin_client, type_key, "check").status_code == 404


def test_the_check_url_takes_only_posts(admin_client):
    assert admin_client.get(f"{URL}list-item/list:int/").status_code == 405


def test_the_check_url_needs_a_login(client):
    response = ask(client, "list:int", "check", value__item="7", items="[]")
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.parametrize("codename", ["change_config", "add_config"])
def test_the_check_url_needs_add_or_change_permission(client, django_user_model, codename):
    user = django_user_model.objects.create_user("staff", password="unused", is_staff=True)
    client.force_login(user)
    fields = {"value__item": "7", "items": "[]", "position": ""}
    assert ask(client, "list:int", "check", **fields).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename=codename))
    assert ask(client, "list:int", "check", **fields).json() == {"text": "7"}


def test_the_check_url_checks_csrf(admin_user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    assert ask(client, "list:int", "check", value__item="7", items="[]").status_code == 403


def test_the_check_url_never_saves(admin_client):
    answer(admin_client, "list:int", "lines", lines='["1"]')
    assert not Config.objects.exists()


# ---- Saving ----


def test_saving_from_the_list_editor_keeps_items_exactly(admin_client):
    # The bug behind the deferred review findings: spaces, empty items and line breaks survive a save.
    texts = ["  INV-", "", "Regards,\nThe team"]
    Config.objects.create(name="NOTES", type="list:text", value=json.dumps(texts))
    content = admin_client.get(change_url("NOTES")).content.decode()
    # An item has a line break, so even without JavaScript the page saves the list, not the text.
    assert 'name="value__mode" value="list"' in content
    assert re.search(r'<textarea name="value"[^>]* readonly', content)
    response = admin_client.post(
        change_url("NOTES"),
        {
            "value": "ignored",
            "value__mode": "list",
            "value__items": json.dumps(texts),
            "description": "",
            "_save": "Save",
        },
    )
    assert response.status_code == 302
    assert json.loads(Config.objects.get(name="NOTES").value) == texts


def test_saving_raw_text_still_works(admin_client):
    response = admin_client.post(
        f"{URL}add/?type=list:int", {"name": "PORTS", "value": "80\n443", "description": "", "_save": "Save"}
    )
    assert response.status_code == 302
    assert Config.objects.get(name="PORTS").value == '["80", "443"]'


def test_an_unreadable_stored_item_is_named_when_saving(admin_client):
    Config.objects.create(name="PORTS", type="list:int", value='["1"]')
    response = admin_client.post(
        change_url("PORTS"),
        {"value__mode": "list", "value__items": '["1", "x"]', "description": "", "_save": "Save"},
    )
    assert response.status_code == 200
    assert "Item 2: Enter a whole number" in response.content.decode()


def test_a_list_that_cant_be_read_shows_the_stored_items_again(admin_client):
    # Review focus: a tampered or truncated request. The page shows the stored list, not an empty one, so saving
    # again keeps it.
    Config.objects.create(name="PORTS", type="list:int", value='["1", "2"]')
    response = admin_client.post(
        change_url("PORTS"),
        {"value": "", "value__mode": "list", "value__items": "[1,", "description": "", "_save": "Save"},
    )
    assert response.status_code == 200
    assert "The list couldn&#x27;t be read. Reload the page and try again." in response.content.decode()
    shown = response.context["adminform"].form["value"].value()
    assert isinstance(shown, StoredTexts)
    assert shown == ["1", "2"]
    assert 'name="value__items" value="[&quot;1&quot;, &quot;2&quot;]"' in response.content.decode()


def test_a_raw_save_names_the_line_a_validator_refuses(admin_client):
    Config.objects.create(name="NAMES", type="list:str", value='["x"]')
    response = admin_client.post(
        change_url("NAMES"), {"value": "a\nb\x00c", "value__mode": "raw", "description": "", "_save": "Save"}
    )
    assert response.status_code == 200
    assert response.context["adminform"].form.errors["value"] == ["Line 2: Null characters are not allowed."]
    assert Config.objects.get(name="NAMES").value == '["x"]'
