from datetime import date

import pytest
from django.core.exceptions import ValidationError

from dynamic_configs.forms.list import LineListField, TypedLineListField
from dynamic_configs.types.builtin import BUILTIN_TYPES

TYPES = {config_type.key: config_type for config_type in BUILTIN_TYPES}


def test_lines_become_stripped_items_and_blank_lines_are_dropped():
    assert LineListField(required=False).clean("  a \n\n b\n   \n") == ["a", "b"]


def test_an_empty_textarea_is_an_empty_list():
    assert LineListField(required=False).clean("") == []


def test_a_required_field_rejects_a_blank_textarea():
    with pytest.raises(ValidationError, match="required"):
        LineListField().clean("\n \n")


def test_validators_run_on_each_item():
    with pytest.raises(ValidationError, match="at most 3"):
        LineListField(max_length=3, required=False).clean("abc\nabcd")


def test_lists_display_one_item_per_line():
    assert LineListField().prepare_value(["a", "b"]) == "a\nb"
    assert LineListField().prepare_value("a\nb") == "a\nb"


def test_typed_items_are_parsed_by_the_item_type():
    assert TypedLineListField(TYPES["int"], required=False).clean("1\n 2 \n") == [1, 2]


def test_typed_errors_name_every_bad_line():
    with pytest.raises(ValidationError) as error:
        TypedLineListField(TYPES["int"], required=False).clean("1\n\nx\ny")
    assert error.value.messages == [
        "Line 3: Enter a whole number, such as 42.",
        "Line 4: Enter a whole number, such as 42.",
    ]


def test_unique_lists_reject_repeats_after_parsing():
    with pytest.raises(ValidationError) as error:
        TypedLineListField(TYPES["int"], unique=True, required=False).clean("1\n2\n01\n2")
    assert error.value.messages == ["Lines 1 and 3 are the same.", "Lines 2 and 4 are the same."]


def test_unique_lists_accept_distinct_items():
    assert TypedLineListField(TYPES["int"], unique=True, required=False).clean("1\n2") == [1, 2]


def test_lists_that_allow_repeats_keep_them():
    assert TypedLineListField(TYPES["int"], required=False).clean("1\n1") == [1, 1]


def test_typed_items_display_as_their_stored_text():
    assert TypedLineListField(TYPES["date"]).prepare_value([date(2026, 11, 2)]) == "2026-11-02"
