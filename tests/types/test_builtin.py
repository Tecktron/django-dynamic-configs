from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django import forms

from dynamic_configs.forms.fields import DurationUnitField, formfield_for
from dynamic_configs.forms.json import JSONTextField
from dynamic_configs.types.builtin import BUILTIN_TYPES

BY_KEY = {config_type.key: config_type for config_type in BUILTIN_TYPES}

SAMPLES = {
    "str": "Example",
    "text": "line one\nline two",
    "int": 42,
    "float": 0.5,
    "decimal": Decimal("19.99"),
    "bool": True,
    "date": date(2026, 11, 2),
    "datetime": datetime(2026, 11, 2, 17, 0, tzinfo=ZoneInfo("America/New_York")),
    "json": {"sizes": [1, 2]},
    "seconds": timedelta(seconds=90),
    "minutes": timedelta(minutes=1.5),
    "hours": timedelta(hours=1.5),
    "days": timedelta(days=2),
    "weeks": timedelta(weeks=1),
}


def test_the_built_in_keys():
    assert set(BY_KEY) == set(SAMPLES)


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_each_built_in_round_trips_a_sample(key):
    config_type = BY_KEY[key]
    assert config_type.from_text(config_type.to_text(SAMPLES[key])) == SAMPLES[key]


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_each_built_in_has_a_label_and_help_text(key):
    assert BY_KEY[key].label
    assert BY_KEY[key].help_text


def test_only_text_and_json_have_no_list_variants():
    assert {key for key, config_type in BY_KEY.items() if not config_type.listable} == {"text", "json"}


EXPECTED_FIELDS = {
    "str": forms.CharField,
    "text": forms.CharField,
    "int": forms.IntegerField,
    "float": forms.FloatField,
    "decimal": forms.DecimalField,
    "bool": forms.BooleanField,
    "date": forms.DateField,
    "datetime": forms.SplitDateTimeField,
    "json": JSONTextField,
    "seconds": DurationUnitField,
    "minutes": DurationUnitField,
    "hours": DurationUnitField,
    "days": DurationUnitField,
    "weeks": DurationUnitField,
}

SUBMITTED = {
    "str": "Example",
    "text": "line one\nline two",
    "int": "42",
    "float": "0.5",
    "decimal": "19.99",
    "bool": "on",
    "date": "2026-11-02",
    "datetime": ["2026-11-02", "17:00"],
    "json": '{"sizes": [1, 2]}',
    "seconds": "90",
    "minutes": "1.5",
    "hours": "1.5",
    "days": "2",
    "weeks": "1",
}


@pytest.mark.parametrize("key", sorted(EXPECTED_FIELDS))
def test_each_built_in_has_its_form_field(key):
    assert type(formfield_for(BY_KEY[key], required=False)) is EXPECTED_FIELDS[key]


@pytest.mark.parametrize("key", sorted(SUBMITTED))
def test_each_built_in_form_field_returns_a_value_of_its_type(key):
    value = formfield_for(BY_KEY[key], required=False).clean(SUBMITTED[key])
    assert BY_KEY[key].coerce(value) == value


def test_text_uses_a_textarea_and_keeps_whitespace():
    field = formfield_for(BY_KEY["text"], required=False)
    assert isinstance(field.widget, forms.Textarea)
    assert field.clean("  indented\n kept  ") == "  indented\n kept  "


@pytest.mark.parametrize("unit", ["seconds", "minutes", "hours", "days", "weeks"])
def test_duration_fields_use_their_unit(unit):
    assert formfield_for(BY_KEY[unit]).unit == unit
