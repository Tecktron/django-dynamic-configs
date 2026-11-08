from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError
from django.http import QueryDict

from dynamic_configs.forms.list import (
    ITEMS_SUFFIX,
    MODE_SUFFIX,
    LineListField,
    ListWidget,
    StoredTexts,
    TypedLineListField,
    UnreadableItems,
    split_lines,
)
from dynamic_configs.types.registry import build_registry

TYPES = build_registry(
    {"color": {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}}
)


def typed(key, **kwargs):
    return TypedLineListField(TYPES.get(key), required=False, **kwargs)


def query(**data):
    result = QueryDict(mutable=True)
    for key, value in data.items():
        result[key] = value
    return result


# ---- Raw text, one item per line ----


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


def test_the_textarea_gets_no_length_limits():
    # They apply to each item, which the browser can't check.
    field = LineListField(max_length=3, min_length=1)
    assert "maxlength" not in field.widget.attrs
    assert "minlength" not in field.widget.attrs


def test_typed_items_are_parsed_by_the_item_type():
    assert typed("int").clean("1\n 2 \n") == [1, 2]


def test_typed_errors_name_every_bad_line():
    with pytest.raises(ValidationError) as error:
        typed("int").clean("1\n\nx\ny")
    assert error.value.messages == [
        "Line 3: Enter a whole number, such as 42.",
        "Line 4: Enter a whole number, such as 42.",
    ]


def test_unique_lists_reject_repeats_after_parsing():
    with pytest.raises(ValidationError) as error:
        typed("int", unique=True).clean("1\n2\n01\n2")
    assert error.value.messages == ["Lines 1 and 3 are the same.", "Lines 2 and 4 are the same."]


def test_unique_lists_accept_distinct_items():
    assert typed("int", unique=True).clean("1\n2") == [1, 2]


def test_lists_that_allow_repeats_keep_them():
    assert typed("int").clean("1\n1") == [1, 1]


@pytest.mark.parametrize(("setting", "expected"), [(None, [" a "]), (False, [" a "]), (True, ["a"])])
def test_raw_string_lines_are_stripped_only_as_strip_strings_says(settings, setting, expected):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": setting}
    assert typed("str").clean(" a \n") == expected


def test_raw_text_lines_are_kept_exactly(settings):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": True}
    assert typed("text").clean("  indented\n") == ["  indented"]


def test_lines_of_spaces_are_blank_lines():
    assert typed("str").clean("a\n   \nb") == ["a", "b"]


def test_lines_split_only_at_line_breaks():
    # Review focus: Windows line endings split, U+2028 (which str.splitlines splits at) doesn't.
    assert split_lines("a\r\nb\rc\nd e") == ["a", "b", "c", "d e"]
    assert typed("str").clean("a\r\nb") == ["a", "b"]


# ---- Stored texts, from the list editor ----


def test_stored_texts_are_read_exactly():
    texts = StoredTexts(["  INV-", "", "PO-"])
    assert typed("str").clean(texts) == ["  INV-", "", "PO-"]


def test_stored_texts_keep_line_breaks():
    assert typed("text").clean(StoredTexts(["Regards,\nThe team"])) == ["Regards,\nThe team"]


def test_stored_text_errors_name_the_item():
    # Review focus: a stored item the type can't read (a hand-edited row).
    with pytest.raises(ValidationError) as error:
        typed("int").clean(StoredTexts(["1", "x"]))
    assert error.value.messages == ["Item 2: Enter a whole number, such as 42."]


def test_stored_text_repeats_name_the_items():
    with pytest.raises(ValidationError) as error:
        typed("int", unique=True).clean(StoredTexts(["1", "2", "1"]))
    assert error.value.messages == ["Items 1 and 3 are the same."]


def test_unreadable_list_data_is_a_form_error():
    # Review focus: a tampered or truncated request.
    with pytest.raises(ValidationError, match="The list couldn't be read"):
        typed("int").clean(UnreadableItems())


def test_lists_display_as_their_stored_texts():
    assert typed("date").prepare_value([date(2026, 11, 2)]) == StoredTexts(["2026-11-02"])
    assert LineListField().prepare_value(["a", "b"]) == ["a", "b"]
    texts = StoredTexts(["x"])
    assert typed("str").prepare_value(texts) is texts
    assert LineListField().prepare_value("a\nb") == "a\nb"


# ---- The widget ----


def test_the_widget_reads_the_textarea_unless_the_mode_says_list():
    widget = ListWidget()
    assert widget.value_from_datadict(query(value="a\nb"), {}, "value") == "a\nb"
    data = query(value="ignored", **{f"value{MODE_SUFFIX}": "list", f"value{ITEMS_SUFFIX}": '["a", ""]'})
    read = widget.value_from_datadict(data, {}, "value")
    assert isinstance(read, StoredTexts)
    assert read == ["a", ""]


# Nested too deeply: Python's JSON reader raises RecursionError, not ValueError.
@pytest.mark.parametrize("items", ["not json", '{"a": 1}', '["a", 2]', "[" * 100000 + "]" * 100000, None])
def test_list_mode_data_that_isnt_an_array_of_strings_is_unreadable(items):
    data = query(**{f"value{MODE_SUFFIX}": "list"})
    if items is not None:
        data[f"value{ITEMS_SUFFIX}"] = items
    assert isinstance(ListWidget().value_from_datadict(data, {}, "value"), UnreadableItems)


def test_the_widget_shows_items_one_per_line_and_says_raw():
    html = ListWidget().render("value", StoredTexts(["a", "b"]))
    assert ">\na\nb</textarea>" in html
    assert 'name="value__items" value="[&quot;a&quot;, &quot;b&quot;]"' in html
    assert 'name="value__mode" value="raw"' in html
    assert "readonly" not in html
    assert "One item per line." in html


def test_text_that_isnt_a_list_yet_has_no_items():
    # Input re-displayed after an error: the editor script starts in raw mode.
    html = ListWidget().render("value", "1\nx")
    assert 'name="value__items" value="null"' in html


def test_a_list_with_a_line_break_item_is_read_only_and_saved_as_a_list():
    html = ListWidget().render("value", StoredTexts(["Regards,\nThe team"]))
    assert "readonly" in html
    assert 'name="value__mode" value="list"' in html
    assert "editing it needs JavaScript" in html


# ---- The item editor's helpers ----


def test_an_item_is_checked_and_returned_as_its_stored_text():
    assert typed("int").item_text(query(value__item="07"), {}, "value__item") == "7"


def test_an_invalid_item_gets_the_types_own_error():
    with pytest.raises(ValidationError, match="Enter a whole number"):
        typed("int").item_text(query(value__item="a"), {}, "value__item")


def test_an_empty_item_is_required_unless_the_type_has_an_empty_value():
    with pytest.raises(ValidationError, match="This field is required."):
        typed("int").item_text(query(value__item=""), {}, "value__item")
    assert typed("str").item_text(query(value__item=""), {}, "value__item") == ""


def test_an_unchecked_boolean_item_is_false():
    assert typed("bool").item_text(query(), {}, "value__item") == "false"


def test_an_item_the_type_rejects_is_an_error():
    # A str item can't contain a line break; its CharField would accept one, the serializer doesn't.
    with pytest.raises(ValidationError, match="single line"):
        typed("str").item_text(query(value__item="a\nb"), {}, "value__item")


@pytest.mark.parametrize(("setting", "expected"), [(None, " a "), (True, "a")])
def test_typed_string_items_follow_strip_strings(settings, setting, expected):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": setting}
    assert typed("str").item_text(query(value__item=" a "), {}, "value__item") == expected


def test_a_set_refuses_a_repeat_but_not_the_item_being_updated():
    field = typed("int", unique=True)
    data = query(value__item="01")
    with pytest.raises(ValidationError, match="That's already in the set."):
        field.item_text(data, {}, "value__item", others=["2", "1"])
    assert field.item_text(data, {}, "value__item", others=["2", "1"], position=1) == "1"
    # An unreadable item (a hand-edited row) is no one's repeat.
    assert field.item_text(data, {}, "value__item", others=["x"]) == "1"


def test_an_item_loads_into_each_of_the_editors_inputs():
    assert typed("int").editor_values("7", "value__item") == {"value__item": "7"}
    assert typed("str").editor_values("", "value__item") == {"value__item": ""}
    assert typed("bool").editor_values("true", "value__item") == {"value__item": True}
    text = TYPES.get("datetime").to_text(datetime(2026, 11, 2, 22, tzinfo=dt_timezone.utc))
    assert typed("datetime").editor_values(text, "value__item") == {
        "value__item_0": "2026-11-02",
        "value__item_1": "17:00:00",
        "value__item_2": "America/New_York",
    }


def test_an_unreadable_item_cant_be_loaded():
    with pytest.raises(ValidationError, match="Enter a whole number"):
        typed("int").editor_values("x", "value__item")


def test_items_sort_by_value_in_either_direction():
    assert typed("int").sorted_texts(["10", "9", "100"], descending=False) == ["9", "10", "100"]
    assert typed("int").sorted_texts(["10", "9", "100"], descending=True) == ["100", "10", "9"]
    assert typed("str").sorted_texts(["b", "A", "a"], descending=False) == ["A", "a", "b"]


def test_items_that_cant_be_compared_cant_be_sorted():
    with pytest.raises(ValidationError, match="These items can't be sorted."):
        typed("color").sorted_texts(["#bbbbbb", "#aaaaaa"], descending=False)


def test_raw_lines_become_stored_texts_or_line_errors():
    assert typed("int").texts_from_lines(["1", " 02 ", ""]) == ["1", "2"]
    with pytest.raises(ValidationError) as error:
        typed("int").texts_from_lines(["1", "x"])
    assert error.value.messages == ["Line 2: Enter a whole number, such as 42."]
