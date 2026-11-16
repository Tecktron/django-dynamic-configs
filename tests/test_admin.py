import html
import re
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from html.parser import HTMLParser

import pytest
from django import forms
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.staticfiles import finders
from django.core import checks
from django.db import IntegrityError
from django.db.models.signals import post_save
from django.test import Client

from dynamic_configs.admin import ConfigAdmin, ConfigAdminMixin, register_admin
from dynamic_configs.forms.config import ConfigAddForm
from dynamic_configs.models import Config
from dynamic_configs.types.registry import get_registry

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


def test_the_plain_admin_has_no_page_of_a_past_version():
    # ConfigAdminMixin.history_form_view serves simple-history's page of a past version, which the plain admin lacks.
    names = {pattern.name for pattern in ConfigAdmin(Config, AdminSite()).get_urls()}
    assert names == {
        "dynamic_configs_config_list_item",
        "dynamic_configs_config_changelist",
        "dynamic_configs_config_add",
        "dynamic_configs_config_history",
        "dynamic_configs_config_delete",
        "dynamic_configs_config_change",
        None,
    }


def test_the_default_admin_passes_its_checks():
    assert ConfigAdmin(Config, AdminSite()).check() == []


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("fields", ("name", "value")),
        ("fieldsets", [(None, {"fields": ("name", "value")})]),
        ("readonly_fields", ("description",)),
    ],
)
def test_the_mixin_warns_about_an_option_it_sets_itself(option, value):
    skinned = type("SkinnedConfigAdmin", (ConfigAdminMixin, admin.ModelAdmin), {option: value})
    [warning] = skinned(Config, AdminSite()).check()
    assert (warning.id, warning.level, warning.obj) == ("dynamic_configs.W001", checks.WARNING, skinned)
    assert warning.msg == f"SkinnedConfigAdmin sets {option}, which ConfigAdminMixin ignores: it sets them itself."
    assert warning.hint == "Override get_fieldsets() or get_readonly_fields() and call super()."


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
        # Deeply nested: Python's reader fails on a small stack and reads nested lists on a large one.
        "[" * 100_000 + "]" * 100_000,
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
    # The server checks the limit itself: a post needn't come from the editor.
    depth = 129
    data = {"name": "DEEP", "value": "[" * depth + "]" * depth, "description": "", "_save": "Save"}
    response = admin_client.post(f"{URL}add/?type=json", data)
    assert response.status_code == 200
    assert "The JSON is nested too deeply: the limit is 128 levels." in response.content.decode()


def test_json_with_a_lone_surrogate_is_a_form_error_not_a_500(admin_client):
    data = {"name": "ODD", "value": '["\\ud800"]', "description": "", "_save": "Save"}
    response = admin_client.post(f"{URL}add/?type=json", data)
    assert response.status_code == 200
    assert "The value can&#x27;t be stored" in response.content.decode()
    assert not Config.objects.filter(name="ODD").exists()


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


def test_whole_numbers_are_marked_for_the_admin_script(admin_client):
    make("MAX_RETRIES", "int", "3")
    content = admin_client.get(change_url("MAX_RETRIES")).content.decode()
    assert re.search(r'<input type="number" name="value" value="3"[^>]* data-dynamic-configs-int', content)
    assert "dynamic_configs/admin.js" in content


@pytest.mark.parametrize(("type_key", "value"), [("float", "1.5"), ("decimal", "1.50"), ("minutes", "1.5")])
def test_numbers_that_take_decimals_arent_marked(admin_client, type_key, value):
    make("AMOUNT", type_key, value)
    assert "data-dynamic-configs-int" not in admin_client.get(change_url("AMOUNT")).content.decode()


def test_decimals_are_marked_for_the_admin_script(admin_client):
    make("PRICE", "decimal", "1.50")
    content = admin_client.get(change_url("PRICE")).content.decode()
    assert re.search(r'<input type="number" name="value" value="1.50"[^>]* data-dynamic-configs-decimal', content)
    assert "dynamic_configs/admin.js" in content


@pytest.mark.parametrize(("type_key", "value"), [("int", "3"), ("float", "1.5"), ("minutes", "1.5")])
def test_numbers_that_arent_decimals_arent_marked_as_decimals(admin_client, type_key, value):
    make("AMOUNT", type_key, value)
    assert "data-dynamic-configs-decimal" not in admin_client.get(change_url("AMOUNT")).content.decode()


MONEY_CURRENCY = {
    "money_currency": {
        "type": "dynamic_configs.types.money.Money",
        "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
        "form": "dynamic_configs.forms.money.MoneyCurrencyField",
        "label": "Money with currency",
    },
}


def input_tag(content, name):
    return re.search(rf"<input [^>]*name=\"{name}\"[^>]*>", content).group(0)


def test_the_admin_marks_a_combined_fields_number_part(admin_client, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY_CURRENCY}
    make("PRICE", "money_currency", "1.00 CAD")
    content = admin_client.get(change_url("PRICE")).content.decode()
    amount, currency = input_tag(content, "value_0"), input_tag(content, "value_1")
    assert 'type="number"' in amount
    assert "data-dynamic-configs-decimal" in amount
    assert 'type="number"' not in currency
    assert "data-dynamic-configs-decimal" not in currency


def test_the_admin_marks_a_list_editors_combined_number_part(admin_client, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY_CURRENCY}
    make("PRICES", "list:money_currency", '["1.00 CAD"]')
    content = admin_client.get(change_url("PRICES")).content.decode()
    amount, currency = input_tag(content, "value__item_0"), input_tag(content, "value__item_1")
    assert 'type="number"' in amount
    assert "data-dynamic-configs-decimal" in amount
    assert "data-dynamic-configs-decimal" not in currency


def test_a_combined_field_with_a_different_number_of_inputs_is_left_alone():
    widget = forms.MultiWidget([forms.NumberInput()])
    field = forms.MultiValueField((forms.DecimalField(), forms.CharField()), widget=widget, require_all_fields=False)
    ConfigAdminMixin._use_admin_widget(field)
    assert type(field.widget.widgets[0]) is forms.NumberInput


def test_a_combined_fields_other_parts_keep_their_widgets():
    widget = forms.MultiWidget([forms.Textarea(), forms.DateInput()])
    field = forms.MultiValueField((forms.CharField(), forms.DateField()), widget=widget, require_all_fields=False)
    ConfigAdminMixin._use_admin_widget(field)
    assert type(field.widget.widgets[0]) is forms.Textarea
    assert type(field.widget.widgets[1]) is forms.DateInput


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


def test_saving_an_unregistered_type_warns_once(admin_client):
    make("THEME", "gone", "dark")
    response = admin_client.post(
        change_url("THEME"), {"allow_null": "", "description": "Old theme", "_continue": "1"}, follow=True
    )
    content = response.content.decode()
    assert "was changed successfully" in content
    assert content.count("isn&#x27;t registered") == 1
    assert Config.objects.get(name="THEME").description == "Old theme"


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


class RenderedForm(HTMLParser):
    """What a browser would submit for the change form as rendered (its fields' values, as the page shows them)."""

    SKIPPED = ("submit", "button", "image", "file", "reset")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.data = {}
        self._in_form = False
        self._select = None
        self._options = []
        self._option = None
        self._textarea = None

    def add(self, name, value):
        self.data.setdefault(name, []).append(value)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self._in_form = attrs.get("id") == "config_form"
        if not self._in_form or "disabled" in attrs:
            return
        if tag == "input" and attrs.get("type") not in self.SKIPPED and attrs.get("name"):
            if attrs.get("type") in ("checkbox", "radio"):
                if "checked" in attrs:
                    self.add(attrs["name"], attrs.get("value", "on"))
            else:
                self.add(attrs["name"], attrs.get("value") or "")
        elif tag == "textarea":
            self._textarea = [attrs.get("name"), ""]
        elif tag == "select":
            self._select = (attrs.get("name"), "multiple" in attrs)
            self._options = []
        elif tag == "option" and self._select is not None:
            self._option = {"value": attrs.get("value"), "selected": "selected" in attrs, "text": ""}
            self._options.append(self._option)

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data
        elif self._option is not None:
            self._option["text"] += data

    def handle_endtag(self, tag):
        if tag == "textarea" and self._textarea is not None:
            name, text = self._textarea
            # A browser drops the newline right after the opening tag.
            self.add(name, text[1:] if text.startswith("\n") else text)
            self._textarea = None
        elif tag == "option":
            self._option = None
        elif tag == "select" and self._select is not None:
            name, multiple = self._select
            chosen = [option for option in self._options if option["selected"]]
            if not multiple and not chosen and self._options:
                chosen = self._options[:1]
            for option in chosen:
                self.add(name, option["value"] if option["value"] is not None else option["text"])
            self._select = None


def rendered_data(content):
    """Return the change page's form as a browser would submit it, one value per name (a list when repeated)."""
    form = RenderedForm()
    form.feed(content)
    return {name: values[0] if len(values) == 1 else values for name, values in form.data.items()}


def save_untouched(admin_client, name, **changes):
    """Open the change page, then submit it as rendered with ``changes`` (the description, by default)."""
    data = rendered_data(admin_client.get(change_url(name)).content.decode())
    data.update({"description": "Edited", "_save": "Save", **changes})
    return admin_client.post(change_url(name), data)


@pytest.mark.parametrize(("type_key", "stored"), [("str", ""), ("list:str", "[]"), ("text", ""), ("list:int", "[]")])
def test_saving_only_the_description_keeps_an_empty_value(admin_client, type_key, stored):
    # F43: an empty value set from code became None on any save, even one that only edited the description.
    make("EMPTY", type_key, stored, allow_null=True)
    assert save_untouched(admin_client, "EMPTY").status_code == 302
    config = Config.objects.get(name="EMPTY")
    assert (config.value, config.description) == (stored, "Edited")


def test_saving_only_the_description_keeps_a_null_value(admin_client):
    make("NOTHING", "str", None, allow_null=True)
    make("NO_LIST", "list:str", None, allow_null=True)
    assert save_untouched(admin_client, "NOTHING").status_code == 302
    assert save_untouched(admin_client, "NO_LIST").status_code == 302
    assert Config.objects.get(name="NOTHING").value is None
    assert Config.objects.get(name="NO_LIST").value is None


def test_turning_allow_null_off_still_applies_the_empty_value_rule(admin_client):
    make("NOTHING", "int", None, allow_null=True)
    response = save_untouched(admin_client, "NOTHING")
    assert response.status_code == 302
    # Left alone, a null stays; turning allow_null off in the same save asks for a value.
    data = rendered_data(admin_client.get(change_url("NOTHING")).content.decode())
    data.pop("allow_null")
    response = admin_client.post(change_url("NOTHING"), {**data, "description": "", "_save": "Save"})
    assert response.status_code == 200
    assert "This field is required." in response.content.decode()
    assert Config.objects.get(name="NOTHING").allow_null is True


SAMPLES = {
    "bool": True,
    "date": date(2026, 3, 4),
    "datetime": datetime(2026, 7, 1, 3, 15, tzinfo=dt_timezone.utc),
    "days": timedelta(days=3),
    "decimal": Decimal("1.50"),
    "float": 1.5,
    "hours": timedelta(hours=36),
    "int": 3,
    "json": {"a": [1, 2]},
    "minutes": timedelta(minutes=90),
    "seconds": timedelta(seconds=45),
    "str": "Example",
    "text": "two\nlines",
    "weeks": timedelta(weeks=2),
}
# The same instants the way a hand-written row or an API call might store them: seconds, fractions, another zone.
EXTRA_SAMPLES = [
    ("datetime", datetime(2026, 7, 1, 3, 15, 45, 123456, tzinfo=dt_timezone.utc)),
    ("datetime", datetime(2026, 1, 1, 0, 0, tzinfo=dt_timezone.utc)),
    ("datetime", datetime(2026, 3, 8, 7, 30, 15, tzinfo=dt_timezone.utc)),
    ("float", 1e-07),
    ("float", 12345678.9),
    ("decimal", Decimal("0.000001")),
    ("str", " padded "),
    ("seconds", timedelta(seconds=1, microseconds=500)),
]
CASES = (
    list(SAMPLES.items())
    + [(f"list:{key}", [value]) for key, value in SAMPLES.items() if key != "json"]
    + [(f"set:{key}", [value]) for key, value in SAMPLES.items() if key != "json"]
    + EXTRA_SAMPLES
)


@pytest.mark.parametrize(("type_key", "value"), CASES, ids=[f"{key}-{n}" for n, (key, _) in enumerate(CASES)])
def test_saving_only_the_description_keeps_the_value_for_every_type(admin_client, type_key, value):
    # Review Focus 3: the value field's posted data is what the page rendered; the stored text must not move.
    stored = get_registry().get(type_key).to_text(value)
    make("SAMPLE", type_key, stored, allow_null=True)
    assert save_untouched(admin_client, "SAMPLE").status_code == 302
    config = Config.objects.get(name="SAMPLE")
    assert (config.value, config.description) == (stored, "Edited")


@pytest.mark.parametrize("type_key", ["bool", "date", "datetime", "int", "str", "list:int", "set:str", "json"])
def test_saving_only_the_description_keeps_a_null_for_every_type(admin_client, type_key):
    make("SAMPLE", type_key, None, allow_null=True)
    assert save_untouched(admin_client, "SAMPLE").status_code == 302
    assert Config.objects.get(name="SAMPLE").value is None


MONEY_TYPES = {
    "money": {
        "type": "decimal.Decimal",
        "serializer": "dynamic_configs.types.money.MoneySerializer",
        "form": "dynamic_configs.forms.money.MoneyField",
    },
    "money_currency": {
        "type": "dynamic_configs.types.money.Money",
        "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
        "form": "dynamic_configs.forms.money.MoneyCurrencyField",
    },
}


@pytest.mark.parametrize(
    ("type_key", "stored"),
    [
        ("money", "9.99"),
        ("money_currency", "9.99 CAD"),
        ("list:money", '["9.99", "1.50"]'),
        ("set:money_currency", '["9.99 CAD"]'),
    ],
)
def test_saving_only_the_description_keeps_a_money_value(admin_client, settings, type_key, stored):
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY_TYPES}
    make("PRICE", type_key, stored)
    assert save_untouched(admin_client, "PRICE").status_code == 302
    assert Config.objects.get(name="PRICE").value == stored


UNREADABLE = [
    ("int", "abc"),
    ("list:int", "oops"),
    ("bool", "maybe"),
    ("date", "someday"),
    ("datetime", "soon"),
    ("float", "many"),
    ("json", "{not json"),
    ("str", "two\nlines"),
    ("set:str", "oops"),
    ("list:str", "[1, 2]"),
]


def stored_notice(content, stored):
    return f"<pre>{html.escape(stored)}</pre>" in content


def test_an_unreadable_value_is_shown_and_not_overwritten(admin_client):
    # F44: the page opened an empty field with no message, and saving anything overwrote the stored text.
    make("MAX_RETRIES", "int", "abc")
    content = admin_client.get(change_url("MAX_RETRIES")).content.decode()
    assert "The stored value can't be read: Enter a whole number, such as 42. It's shown below" in content
    assert "enter a new value to replace it." in content
    assert stored_notice(content, "abc")
    assert rendered_data(content)["value"] == ""
    response = save_untouched(admin_client, "MAX_RETRIES")
    assert response.status_code == 200
    assert "Enter a value to replace the unreadable one." in response.content.decode()
    config = Config.objects.get(name="MAX_RETRIES")
    assert (config.value, config.description) == ("abc", "")


def test_an_unreadable_list_is_shown_and_not_overwritten(admin_client):
    make("PORTS", "list:int", "oops")
    content = admin_client.get(change_url("PORTS")).content.decode()
    assert "The stored value can't be read: A list must be stored as a JSON array." in content
    assert stored_notice(content, "oops")
    response = save_untouched(admin_client, "PORTS")
    assert response.status_code == 200
    assert "Enter a value to replace the unreadable one." in response.content.decode()
    assert Config.objects.get(name="PORTS").value == "oops"


def test_entering_a_value_replaces_an_unreadable_one(admin_client):
    make("MAX_RETRIES", "int", "abc")
    make("PORTS", "list:int", "oops")
    assert save_untouched(admin_client, "MAX_RETRIES", value="5").status_code == 302
    assert save_untouched(admin_client, "PORTS", value="80\n443").status_code == 302
    assert Config.objects.get(name="MAX_RETRIES").value == "5"
    assert Config.objects.get(name="PORTS").value == '["80", "443"]'


@pytest.mark.parametrize(("type_key", "stored"), UNREADABLE)
def test_the_notice_shows_for_every_kind_of_field(admin_client, type_key, stored):
    make("BROKEN", type_key, stored)
    content = admin_client.get(change_url("BROKEN")).content.decode()
    assert "The stored value can't be read: " in content
    assert stored_notice(content, stored)
    assert save_untouched(admin_client, "BROKEN").status_code == 200
    assert Config.objects.get(name="BROKEN").value == stored


@pytest.mark.parametrize(("type_key", "stored"), UNREADABLE + [("days", "soon"), ("money_currency", "lots")])
def test_an_unreadable_value_is_refused_when_the_config_allows_null_too(admin_client, settings, type_key, stored):
    # Left as the page showed it (empty, a zone chosen), the value is unchanged: refused, not turned into None.
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY_TYPES}
    make("BROKEN", type_key, stored, allow_null=True)
    response = save_untouched(admin_client, "BROKEN", allow_null="on")
    assert response.status_code == 200
    assert "Enter a value to replace the unreadable one." in response.content.decode()
    assert Config.objects.get(name="BROKEN").value == stored


def test_the_notice_shows_for_money(admin_client, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY_TYPES}
    make("PRICE", "money_currency", "lots")
    content = admin_client.get(change_url("PRICE")).content.decode()
    assert "The stored value can't be read: " in content
    assert stored_notice(content, "lots")
    assert save_untouched(admin_client, "PRICE").status_code == 200
    assert Config.objects.get(name="PRICE").value == "lots"


def test_the_notice_shows_for_a_nullable_boolean(admin_client):
    make("BETA", "bool", "maybe", allow_null=True)
    content = admin_client.get(change_url("BETA")).content.decode()
    assert "The stored value can't be read: " in content
    assert save_untouched(admin_client, "BETA").status_code == 200
    assert Config.objects.get(name="BETA").value == "maybe"


def test_the_stored_text_in_the_notice_is_escaped(admin_client):
    make("MAX_RETRIES", "int", "<script>alert(1)</script>")
    content = admin_client.get(change_url("MAX_RETRIES")).content.decode()
    assert "<script>alert(1)</script>" not in content
    assert "<pre>&lt;script&gt;alert(1)&lt;/script&gt;</pre>" in content


def test_a_failed_save_shows_the_notice_again(admin_client):
    make("MAX_RETRIES", "int", "abc")
    response = save_untouched(admin_client, "MAX_RETRIES")
    assert stored_notice(response.content.decode(), "abc")


def test_a_list_with_a_bad_item_still_opens_as_items(admin_client):
    # Not an F44 case: the stored text is a JSON array of strings, so the editor shows each item to fix.
    make("PORTS", "list:int", '["1", "x"]')
    content = admin_client.get(change_url("PORTS")).content.decode()
    assert "The stored value can't be read" not in content
    assert "dynamic-configs-list" in content


def test_a_user_without_permission_sees_no_unregistered_warning(admin_client, django_user_model):
    # F45: the warning was queued before the permission check, so it showed on the page after the 403.
    make("THEME", "gone", "dark")
    staff = django_user_model.objects.create_user("staff", password="unused", is_staff=True)
    client = Client()
    client.force_login(staff)
    assert client.get(change_url("THEME")).status_code == 403
    content = client.get("/admin/").content.decode()
    assert "isn&#x27;t registered" not in content
    assert "gone" not in content


def test_adding_a_name_taken_meanwhile_is_a_form_error(admin_client, mocker):
    # F46: two adds of one name raced: the second got a server error. Here the row appears after the form's own
    # check (which is skipped once), so the save itself meets it.
    make("MAX_RETRIES", "int", "3")
    original = ConfigAddForm.validate_unique
    checks = iter([None])

    def validate_unique(form):
        if next(checks, "later") is None:
            return None
        return original(form)

    mocker.patch.object(ConfigAddForm, "validate_unique", validate_unique)
    response = admin_client.post(
        f"{URL}add/?type=int", {"name": "MAX_RETRIES", "value": "9", "description": "", "_save": "Save"}
    )
    assert response.status_code == 200
    assert "already exists" in response.content.decode()
    # Nothing was overwritten, and the request's own transaction is still usable.
    assert Config.objects.get(name="MAX_RETRIES").value == "3"


def test_an_add_never_overwrites_a_row_created_meanwhile(admin_client, mocker):
    # With the form's check always skipped, the save meets the row both times and the error is raised: the row is
    # never updated in its place.
    make("MAX_RETRIES", "int", "3")
    mocker.patch.object(ConfigAddForm, "validate_unique", return_value=None)
    with pytest.raises(IntegrityError):
        admin_client.post(
            f"{URL}add/?type=int", {"name": "MAX_RETRIES", "value": "9", "description": "", "_save": "Save"}
        )
    assert Config.objects.get(name="MAX_RETRIES").value == "3"


def test_an_add_that_fails_for_another_reason_raises(admin_client, mocker):
    # Only a taken name becomes a form error: an IntegrityError with no row of that name behind it still raises.
    mocker.patch.object(Config, "save", side_effect=IntegrityError)
    with pytest.raises(IntegrityError):
        admin_client.post(f"{URL}add/?type=int", {"name": "NEW_ONE", "value": "9", "description": "", "_save": "Save"})
    assert not Config.objects.filter(name="NEW_ONE").exists()


def test_a_receiver_that_saves_again_doesnt_break_an_add(admin_client):
    # The insert is forced for the first save only: a post_save receiver's own save updates the row as usual.
    seen = []

    def resave(sender, instance, created, **kwargs):
        seen.append("save" in vars(instance))
        if created:
            instance.description = "Set by a receiver"
            instance.save()

    post_save.connect(resave, sender=Config)
    try:
        response = admin_client.post(
            f"{URL}add/?type=int", {"name": "MAX_RETRIES", "value": "9", "description": "", "_save": "Save"}
        )
    finally:
        post_save.disconnect(resave, sender=Config)
    assert response.status_code == 302
    assert Config.objects.get(name="MAX_RETRIES").description == "Set by a receiver"
    assert seen == [False, False]
