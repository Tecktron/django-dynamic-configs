import logging

import pytest

from dynamic_configs.types.registry import (
    Registry,
    TypeConfigError,
    build_registry,
    get_registry,
    list_variant,
    load_custom_type,
    reset_registry,
    set_variant,
)
from tests.custom_types import Color, ColorField, ColorSerializer

COLOR = {
    "type": "tests.custom_types.Color",
    "serializer": "tests.custom_types.ColorSerializer",
    "form": "tests.custom_types.ColorField",
    "label": "Color",
    "help_text": "A hex color, e.g. #1a2b3c.",
    "raw_help_text": "A hex color typed with its #, e.g. #1a2b3c.",
}
PLAIN = {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}


def test_custom_types_are_loaded_from_dotted_paths():
    color = load_custom_type("color", COLOR)
    assert color.python_type is Color
    assert isinstance(color.serializer, ColorSerializer)
    assert color.form_class is ColorField
    assert (color.label, color.help_text, color.listable) == ("Color", "A hex color, e.g. #1a2b3c.", True)
    assert color.raw_help_text == "A hex color typed with its #, e.g. #1a2b3c."


def test_label_help_text_form_and_listable_are_optional():
    plain = load_custom_type("plain", PLAIN)
    assert (plain.label, plain.help_text, plain.form_class, plain.listable) == ("plain", "", None, True)
    assert plain.raw_help_text == ""


@pytest.mark.parametrize(
    ("key", "entry", "check_id", "message"),
    [
        ("2color", COLOR, "E001", "start with a letter"),
        ("list:color", COLOR, "E001", "start with a letter"),
        (5, COLOR, "E001", "start with a letter"),
        ("color", "tests.custom_types.Color", "E001", "must be a dict"),
        ("color", {**COLOR, "colour": "x"}, "E001", "unknown keys: 'colour'"),
        ("color", {"serializer": COLOR["serializer"]}, "E001", "\\['type'\\] must be a dotted path"),
        ("color", {**COLOR, "serializer": 5}, "E001", "\\['serializer'\\] must be a dotted path"),
        ("color", {**COLOR, "type": "tests.custom_types.Missing"}, "E002", "can't import"),
        ("color", {**COLOR, "type": "tests.broken_type_module.Color"}, "E002", "can't import.*ZeroDivisionError"),
        ("color", {**COLOR, "type": "tests.custom_types.not_a_class"}, "E001", "\\['type'\\] must be a class"),
        ("color", {**COLOR, "serializer": "tests.custom_types.not_a_class"}, "E003", "must be a class"),
        ("color", {**COLOR, "serializer": "tests.custom_types.NeedsArgumentSerializer"}, "E003", "no arguments"),
        (
            "color",
            {**COLOR, "serializer": "tests.custom_types.NoMethodsSerializer"},
            "E003",
            "serialize\\(\\) and deserialize\\(\\)",
        ),
        ("color", {**COLOR, "form": 5}, "E001", "\\['form'\\] must be a dotted path"),
        ("color", {**COLOR, "form": "tests.custom_types.MissingField"}, "E002", "can't import"),
        ("color", {**COLOR, "form": "tests.custom_types.not_a_class"}, "E004", "django.forms.Field subclass"),
        ("color", {**COLOR, "form": "tests.custom_types.Color"}, "E004", "django.forms.Field subclass"),
        ("color", {**COLOR, "label": 5}, "E001", "must be strings"),
        ("color", {**COLOR, "help_text": None}, "E001", "must be strings"),
        ("color", {**COLOR, "raw_help_text": 5}, "E001", "'raw_help_text' must be strings"),
        ("color", {**COLOR, "listable": "yes"}, "E001", "a boolean"),
        (
            "color",
            {**COLOR, "sort_key": "tests.custom_types.color_hex", "sort_compare": "tests.custom_types.compare_colors"},
            "E001",
            "Give 'sort_key' or 'sort_compare', not both",
        ),
        ("color", {**COLOR, "sort_key": 5}, "E001", "\\['sort_key'\\] must be a dotted path"),
        (
            "color",
            {**COLOR, "sort_compare": "tests.custom_types.NOT_CALLABLE"},
            "E001",
            "\\['sort_compare'\\] must be callable",
        ),
        ("color", {**COLOR, "sort_key": "tests.custom_types.missing_key"}, "E002", "can't import"),
    ],
)
def test_invalid_custom_types_raise_with_their_check_id(key, entry, check_id, message):
    with pytest.raises(TypeConfigError, match=message) as error:
        load_custom_type(key, entry)
    assert error.value.check_id == f"dynamic_configs.{check_id}"


def test_list_and_set_variants_wrap_the_item_type():
    color = load_custom_type("color", COLOR)
    as_list, as_set = list_variant(color), set_variant(color)
    assert (as_list.key, as_list.label, as_list.container, as_list.item_type) == (
        "list:color",
        "List of Color",
        "list",
        color,
    )
    assert (as_set.key, as_set.label, as_set.container, as_set.python_type) == (
        "set:color",
        "Set of Color",
        "set",
        frozenset,
    )
    assert as_list.help_text == "Each item: A hex color, e.g. #1a2b3c."
    assert as_set.help_text == "No repeats. Each item: A hex color, e.g. #1a2b3c."
    assert not as_list.listable
    assert not as_set.listable


def test_variant_help_text_without_item_help_text():
    plain = load_custom_type("plain", PLAIN)
    assert list_variant(plain).help_text == ""
    assert set_variant(plain).help_text == "No repeats."


def test_the_registry_has_built_ins_and_their_variants():
    registry = build_registry({})
    assert registry.get("int").label == "Integer"
    assert "list:int" in registry
    assert "set:hours" in registry
    assert "list:text" in registry
    assert "set:text" in registry
    assert "set:json" not in registry
    assert registry.get("nope") is None


def test_custom_types_join_the_registry_with_variants():
    registry = build_registry({"color": COLOR})
    assert registry.get("color").python_type is Color
    assert "list:color" in registry
    assert "set:color" in registry


def test_unhashable_custom_types_get_lists_but_not_sets():
    registry = build_registry(
        {"thing": {"type": "tests.custom_types.Unhashable", "serializer": "tests.custom_types.UnhashableSerializer"}}
    )
    assert "list:thing" in registry
    assert "set:thing" not in registry


def test_unlistable_custom_types_get_no_variants():
    registry = build_registry({"color": {**COLOR, "listable": False}})
    assert "list:color" not in registry


def test_a_custom_type_can_replace_a_built_in():
    assert build_registry({"str": COLOR}).get("str").python_type is Color


def test_types_setting_must_be_a_dict():
    with pytest.raises(TypeConfigError, match="must be a dict") as error:
        build_registry(["color"])
    assert error.value.check_id == "dynamic_configs.E001"


def test_iteration_is_sorted_by_label():
    registry = Registry(load_custom_type(key, {**COLOR, "label": key}) for key in ("b", "A", "c"))
    assert [config_type.label for config_type in registry] == ["A", "b", "c"]


def test_get_registry_builds_once_and_logs(caplog):
    caplog.set_level(logging.DEBUG, logger="dynamic_configs")
    reset_registry()
    first = get_registry()
    assert get_registry() is first
    assert [record.getMessage() for record in caplog.records] == [
        f"Built the config type registry ({len(list(first))} types)"
    ]


def test_changing_dynamic_configs_rebuilds_the_registry(settings):
    first = get_registry()
    settings.DYNAMIC_CONFIGS = {"TYPES": {"color": COLOR}}
    assert get_registry() is not first
    assert "color" in get_registry()


def test_changing_other_settings_keeps_the_registry(settings):
    first = get_registry()
    settings.USE_TZ = True
    assert get_registry() is first


def test_a_broken_custom_type_is_skipped_at_runtime_with_an_error(settings, caplog):
    # Review finding: one bad TYPES entry made every get() raise; system checks don't run under gunicorn/uwsgi.
    settings.DYNAMIC_CONFIGS = {"TYPES": {"broken": {**PLAIN, "type": "tests.custom_types.Missing"}, "color": COLOR}}
    registry = get_registry()
    assert "broken" not in registry
    assert "color" in registry
    assert "int" in registry
    [error] = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert "can't import" in error.getMessage()
    assert "dynamic_configs.E002" in error.getMessage()


def test_a_custom_type_whose_module_fails_to_import_is_skipped_at_runtime(settings, caplog):
    # Docstring audit: only ImportError was caught, so a module raising anything else while imported made every get()
    # raise, despite the non-strict build.
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {"broken": {**PLAIN, "type": "tests.broken_type_module.Color"}, "color": COLOR}
    }
    registry = get_registry()
    assert "broken" not in registry
    assert "color" in registry
    [error] = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert "can't import 'tests.broken_type_module.Color' (ZeroDivisionError:" in error.getMessage()
    assert "dynamic_configs.E002" in error.getMessage()


def test_a_types_setting_that_is_not_a_dict_is_ignored_at_runtime(settings, caplog):
    settings.DYNAMIC_CONFIGS = {"TYPES": ["color"]}
    assert "int" in get_registry()
    assert "must be a dict" in caplog.text


def test_a_strict_build_still_raises_for_a_broken_custom_type():
    with pytest.raises(TypeConfigError, match="can't import") as error:
        build_registry({"broken": {**PLAIN, "type": "tests.custom_types.Missing"}})
    assert error.value.check_id == "dynamic_configs.E002"


def test_a_sort_key_is_loaded_from_its_dotted_path():
    color = load_custom_type("color", {**COLOR, "sort_key": "tests.custom_types.color_hex"})
    assert color.sortable
    assert color.sort([Color("#bbbbbb"), Color("#aaaaaa")]) == [Color("#aaaaaa"), Color("#bbbbbb")]


def test_a_compare_function_becomes_a_key():
    color = load_custom_type("color", {**COLOR, "sort_compare": "tests.custom_types.compare_colors"})
    assert color.sort([Color("#bbbbbb"), Color("#aaaaaa")], descending=True) == [Color("#bbbbbb"), Color("#aaaaaa")]


def test_without_a_key_a_type_sorts_only_if_its_values_have_an_order():
    assert load_custom_type("color", COLOR).sort_key is None
    assert not load_custom_type("color", COLOR).sortable
