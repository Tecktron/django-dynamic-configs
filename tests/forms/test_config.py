import pytest
from django import forms

from dynamic_configs.forms.config import ConfigChangeForm, ConfigTypeForm, add_form_for, change_form_for
from dynamic_configs.forms.list import TypedLineListField
from dynamic_configs.models import Config
from dynamic_configs.types.registry import get_registry

pytestmark = pytest.mark.django_db


def add_form(type_key="str", **data):
    fields = {"name": "SITE_NAME", "value": "", "description": ""}
    fields.update(data)
    return add_form_for(get_registry().get(type_key))(data=fields)


def change_form(config, **data):
    fields = {"value": "", "description": ""}
    fields.update(data)
    return change_form_for(config)(data=fields, instance=config)


def make(name="SITE_NAME", type_key="str", value="Example", **fields):
    return Config.objects.create(name=name, type=type_key, value=value, **fields)


def opened(config):
    """Return the change form as the admin opens it: unbound, for the existing config."""
    return change_form_for(config)(instance=config)


def test_the_type_step_offers_the_registered_types_after_a_blank():
    choices = ConfigTypeForm().fields["type"].choices
    assert choices[0] == ("", "---------")
    assert dict(choices)["int"] == "Integer"
    assert dict(choices)["set:str"] == "Set of String"


def test_the_type_step_rejects_an_unknown_type():
    form = ConfigTypeForm(data={"type": "nope"})
    assert not form.is_valid()
    assert "type" in form.errors


def test_the_add_form_uses_the_types_field_and_sets_the_type():
    form = add_form("date")
    assert form.fields["value"].__class__.__name__ == "DateField"
    assert form.fields["value"].help_text == "A date as YYYY-MM-DD, e.g. 2026-11-02."
    assert form.instance.type == "date"


def test_adding_stores_the_value_as_text():
    form = add_form("int", name="MAX_RETRIES", value="42", description="Retries.")
    assert form.is_valid(), form.errors
    config = form.save()
    assert (config.type, config.value, config.description) == ("int", "42", "Retries.")


def test_adding_a_list_takes_one_item_per_line():
    form = add_form("list:str", name="HOSTS", value="a.example\n\nb.example\n")
    assert form.is_valid(), form.errors
    assert form.save().value == '["a.example", "b.example"]'


def test_adding_reports_bad_lines():
    form = add_form("list:int", value="1\nx")
    assert not form.is_valid()
    assert form.errors["value"] == ["Line 2: Enter a whole number, such as 42."]


def test_adding_reports_a_bad_value():
    form = add_form("int", value="forty-two")
    assert not form.is_valid()
    assert form.errors["value"] == ["Enter a whole number."]


@pytest.mark.parametrize(
    ("type_key", "allow_null", "stored"),
    [
        ("str", False, ""),
        ("list:int", False, "[]"),
        ("set:str", False, "[]"),
        ("int", True, None),
        ("str", True, None),
        ("bool", True, None),
    ],
)
def test_adding_an_empty_value(type_key, allow_null, stored):
    data = {"allow_null": "on"} if allow_null else {}
    form = add_form(type_key, value="", **data)
    assert form.is_valid(), form.errors
    assert form.save().value == stored


@pytest.mark.parametrize("type_key", ["int", "bool"])
def test_an_empty_value_is_required_for_other_types(type_key):
    form = add_form(type_key, value="")
    assert not form.is_valid()
    assert form.errors["value"] == ["This field is required."]


def test_a_bool_is_added_with_a_yes_no_unknown_choice():
    # The add page can't know allow_null until it's submitted, so a boolean must be able to be left empty.
    form = add_form("bool", value="true")
    assert isinstance(form.fields["value"], forms.NullBooleanField)
    assert form.is_valid(), form.errors
    assert form.save().value == "true"


def test_names_are_validated_and_unique():
    make()
    assert "name" in add_form(name="SITE_NAME", value="x").errors
    assert "name" in add_form(name="site_name", value="x").errors


def test_an_unregistered_type_gets_the_plain_change_form():
    config = make("THEME", "gone", "dark")
    assert change_form_for(config) is ConfigChangeForm
    assert ConfigChangeForm(data={"value": "dark", "description": ""}, instance=config).is_valid()


def test_the_change_form_uses_the_types_field_and_shows_the_value():
    form = opened(make("MAX_RETRIES", "int", "3"))
    assert form.fields["value"].__class__.__name__ == "IntegerField"
    assert form.initial["value"] == 3
    assert form.fields["value"].help_text == "A whole number, e.g. 42."


def test_a_set_is_shown_in_the_order_it_was_entered():
    form = opened(make("HOSTS", "set:str", '["b.example", "a.example"]'))
    assert isinstance(form.fields["value"], TypedLineListField)
    assert form.initial["value"] == ["b.example", "a.example"]
    assert form["value"].value() == "b.example\na.example"


def test_an_unreadable_value_opens_empty():
    # Review focus: the change page must open, not crash, so the admin can fix the value.
    form = opened(make("MAX_RETRIES", "int", "three"))
    assert form.initial["value"] is None


def test_an_empty_value_opens_empty():
    form = opened(make(value=None, allow_null=True))
    assert form.initial["value"] is None


def test_changing_stores_the_new_text():
    config = make("MAX_RETRIES", "int", "3")
    form = change_form(config, value="5")
    assert form.is_valid(), form.errors
    assert form.save().value == "5"


def test_a_value_the_serializer_rejects_is_a_form_error():
    # Review focus: the CharField accepts a line break, the str serializer doesn't.
    form = change_form(make(), value="two\nlines")
    assert not form.is_valid()
    assert form.errors["value"] == ["A string setting must be a single line; use the Text type for several lines."]


def test_turning_allow_null_off_with_an_empty_value_is_required():
    # Review focus: allow_null changes in the same save, so the rule must use the submitted flag.
    form = change_form(make("MAX_RETRIES", "int", None, allow_null=True), value="")
    assert not form.is_valid()
    assert form.errors["value"] == ["This field is required."]


def test_an_empty_value_with_allow_null_is_stored_as_none():
    form = change_form(make("MAX_RETRIES", "int", "3"), value="", allow_null="on")
    assert form.is_valid(), form.errors
    config = form.save()
    assert (config.value, config.allow_null) == (None, True)


def test_a_field_error_is_reported_once():
    form = change_form(make("MAX_RETRIES", "int", "3"), value="forty-two")
    assert not form.is_valid()
    assert form.errors["value"] == ["Enter a whole number."]


def test_a_custom_field_returning_the_wrong_type_is_a_form_error(settings):
    # Review focus: the admin applies the same type check as the API.
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {
            "color": {
                "type": "tests.custom_types.Color",
                "serializer": "tests.custom_types.ColorSerializer",
                "form": "tests.custom_types.WrongTypeColorField",
            }
        }
    }
    form = change_form(make("BRAND", "color", "#1a2b3c"), value="#ffffff")
    assert not form.is_valid()
    assert form.errors["value"] == ["Type 'color' expects Color, not str."]


def test_names_are_stripped():
    form = add_form(name="  SITE_NAME  ", value="x")
    assert form.is_valid(), form.errors
    assert form.save().name == "SITE_NAME"


def test_adding_a_string_strips_it():
    form = add_form(value="  Example  ")
    assert form.is_valid(), form.errors
    assert form.save().value == "Example"


def test_adding_only_spaces_to_a_string_stores_the_empty_string():
    form = add_form(value="   ")
    assert form.is_valid(), form.errors
    assert form.save().value == ""


def test_adding_text_keeps_its_whitespace():
    form = add_form("text", value="  indented\n\n")
    assert form.is_valid(), form.errors
    assert form.save().value == "  indented\n\n"


def test_changing_a_string_strips_it():
    form = change_form(make(), value="  New  ")
    assert form.is_valid(), form.errors
    assert form.save().value == "New"


def test_descriptions_are_kept_as_typed():
    added = add_form(value="x", description="  Notes,\n  indented.\n")
    assert added.is_valid(), added.errors
    assert added.save().description == "  Notes,\n  indented.\n"
    changed = change_form(make("OTHER"), value="x", description="  kept  ")
    assert changed.is_valid(), changed.errors
    assert changed.save().description == "  kept  "


def test_a_form_without_a_description_field_still_works():
    # A skin may drop the description from its fieldsets; the form must not assume the field is there.
    class ValueOnly(ConfigChangeForm):
        class Meta(ConfigChangeForm.Meta):
            fields = ("value", "allow_null")

    assert "description" not in ValueOnly().fields
