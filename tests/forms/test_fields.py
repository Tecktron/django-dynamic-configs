from datetime import date, timedelta

import pytest
from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.forms.fields import DurationUnitField, SerializerField, formfield_for, strips_typed_strings
from dynamic_configs.forms.json import JSONTextField
from dynamic_configs.forms.list import TypedLineListField
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.registry import build_registry, load_custom_type
from dynamic_configs.types.serializers import BoolSerializer, DateSerializer, IntSerializer
from tests.custom_types import ColorField

PLAIN_COLOR = {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}


def test_serializer_fields_parse_with_the_serializer():
    assert SerializerField(IntSerializer()).clean(" 42 ") == 42


def test_an_empty_serializer_field_is_none():
    assert SerializerField(IntSerializer(), required=False).clean("") is None


def test_serializer_rejections_are_form_errors():
    with pytest.raises(ValidationError, match="whole number"):
        SerializerField(IntSerializer()).clean("forty-two")


def test_serializer_fields_show_values_as_their_text():
    field = SerializerField(DateSerializer())
    assert field.prepare_value(date(2026, 11, 2)) == "2026-11-02"
    assert field.prepare_value("as typed") == "as typed"
    assert field.prepare_value(None) is None


def test_duration_fields_take_a_number_of_their_unit():
    field = DurationUnitField("hours")
    assert field.unit == "hours"
    assert field.clean("1.5") == timedelta(hours=1.5)
    assert field.prepare_value(timedelta(minutes=90)) == "1.5"


def test_json_fields_parse_objects_and_show_them_indented():
    field = JSONTextField()
    assert isinstance(field.widget, forms.Textarea)
    assert field.clean('{"a": [1]}') == {"a": [1]}
    assert field.prepare_value({"a": [1]}) == '{\n  "a": [\n    1\n  ]\n}'
    assert field.prepare_value('{"as": "typed"}') == '{"as": "typed"}'


def test_json_fields_mark_their_textarea_for_the_admin_editor():
    # The admin's script finds the textarea by the marker; outside the admin there's no script to load.
    widget = JSONTextField().widget
    html = widget.render("value", '{"a": 1}')
    assert "data-dynamic-configs-json" in html
    assert 'data-dynamic-configs-json-max-depth="128"' in html
    assert 'spellcheck="false"' in html
    assert not widget.media._js


def test_containers_get_a_typed_line_list():
    field = formfield_for(build_registry({}).get("set:int"), required=False)
    assert isinstance(field, TypedLineListField)
    assert field.unique
    assert field.item_type.key == "int"
    assert not formfield_for(build_registry({}).get("list:int")).unique


def test_types_without_a_form_class_get_a_serializer_field():
    color = load_custom_type("color", PLAIN_COLOR)
    field = formfield_for(color, required=False)
    assert isinstance(field, SerializerField)
    assert field.serializer is color.serializer


def test_a_types_form_class_is_used_with_the_given_options():
    color = load_custom_type("color", {**PLAIN_COLOR, "form": "tests.custom_types.ColorField"})
    field = formfield_for(color, required=False, label="Value", help_text="A color.")
    assert isinstance(field, ColorField)
    assert (field.required, field.label, field.help_text) == (False, "Value", "A color.")


def test_booleans_that_allow_null_get_a_three_way_field():
    flag = ConfigType("flag", "Flag", bool, BoolSerializer(), form_class=forms.BooleanField)
    assert type(formfield_for(flag, required=False)) is forms.BooleanField
    assert type(formfield_for(flag, allow_null=True, required=False)) is forms.NullBooleanField


@pytest.mark.parametrize(
    ("allow_null", "help_text"),
    [
        (False, "Checked means true."),
        (True, "Unknown leaves the setting empty, which needs Allow null checked."),
    ],
)
def test_the_boolean_describes_its_checkbox_or_select_not_typed_text(allow_null, help_text):
    # The type's help ("true or false (yes/no, …)") describes typing, which a checkbox or select doesn't take.
    boolean = build_registry({}).get("bool")
    field = formfield_for(boolean, allow_null=allow_null, help_text=boolean.help_text)
    assert field.help_text == help_text


@pytest.mark.parametrize(("key", "help_text"), [("list:bool", ""), ("set:int", "No repeats.")])
def test_a_lists_field_help_is_only_what_holds_in_both_modes(key, help_text):
    # The item editor and the raw textarea each carry their own help (see the list field).
    config_type = build_registry({}).get(key)
    assert formfield_for(config_type, help_text=config_type.help_text).help_text == help_text


def test_a_custom_boolean_keeps_its_own_help():
    flag = ConfigType("flag", "Flag", bool, BoolSerializer(), form_class=forms.BooleanField)
    assert formfield_for(flag, help_text="Turns the beta on.").help_text == "Turns the beta on."


@pytest.mark.parametrize(
    ("setting", "single", "item"), [(None, True, False), (True, True, True), (False, False, False)]
)
def test_strip_strings_decides_how_typed_strings_are_stripped(settings, setting, single, item):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": setting}
    assert strips_typed_strings(item=False) is single
    assert strips_typed_strings(item=True) is item


@pytest.mark.parametrize("key", ["str", "plain"])
@pytest.mark.parametrize("setting", [None, True, False])
def test_single_line_string_fields_follow_strip_strings(settings, setting, key):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": setting}
    # str has a CharField; a custom type without a form gets a SerializerField (a text input).
    config_type = build_registry({"plain": PLAIN_COLOR}).get(key)
    assert formfield_for(config_type).strip is strips_typed_strings(item=False)
    assert formfield_for(config_type, item=True).strip is strips_typed_strings(item=True)


@pytest.mark.parametrize("setting", [None, True, False])
def test_a_custom_form_field_keeps_its_own_strip(settings, setting):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": setting}
    registry = build_registry(
        {
            "stripped": {**PLAIN_COLOR, "form": "tests.custom_types.ColorField"},
            "unstripped": {**PLAIN_COLOR, "form": "tests.custom_types.UnstrippedColorField"},
        }
    )
    for item in (False, True):
        assert formfield_for(registry.get("stripped"), item=item).strip is True
        assert formfield_for(registry.get("unstripped"), item=item).strip is False


def test_a_projects_replacement_str_with_its_own_form_keeps_its_own_strip(settings):
    # Only the built-in str follows STRIP_STRINGS; a TYPES entry replacing it with its own form is a custom form.
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": True}
    replacement = {
        "type": "builtins.str",
        "serializer": "dynamic_configs.types.serializers.StrSerializer",
        "form": "tests.custom_types.UnstrippedColorField",
    }
    registry = build_registry({"str": replacement})
    assert formfield_for(registry.get("str")).strip is False
    assert formfield_for(registry.get("str"), item=True).strip is False
    assert formfield_for(registry.get("list:str")).item_field.strip is False


def test_a_duration_field_keeps_its_own_strip(settings):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": False}
    field = formfield_for(build_registry({}).get("hours"))
    assert isinstance(field, DurationUnitField)
    assert field.strip is True


def test_multi_line_text_is_never_stripped(settings):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": True}
    text = build_registry({}).get("text")
    assert formfield_for(text).strip is False
    assert formfield_for(text, item=True).strip is False
