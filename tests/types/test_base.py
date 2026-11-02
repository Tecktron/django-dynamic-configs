from datetime import date, datetime
from decimal import Decimal

import pytest

from dynamic_configs.exceptions import ConfigTypeError, ConfigValueError
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.serializers import (
    DateSerializer,
    DecimalSerializer,
    FloatSerializer,
    IntSerializer,
    JSONSerializer,
    ListSerializer,
    SetSerializer,
    StrSerializer,
)

INT = ConfigType("int", "Integer", int, IntSerializer())
FLOAT = ConfigType("float", "Float", float, FloatSerializer())
DECIMAL = ConfigType("decimal", "Decimal", Decimal, DecimalSerializer())
DATE = ConfigType("date", "Date", date, DateSerializer())
STR = ConfigType("str", "String", str, StrSerializer())
JSON = ConfigType("json", "JSON", (dict, list), JSONSerializer(), listable=False)
LIST_INT = ConfigType(
    "list:int",
    "List of Integer",
    list,
    ListSerializer(IntSerializer()),
    listable=False,
    item_type=INT,
    container="list",
)
SET_STR = ConfigType(
    "set:str",
    "Set of String",
    frozenset,
    SetSerializer(StrSerializer()),
    listable=False,
    item_type=STR,
    container="set",
)


class Unhashable:
    __hash__ = None


@pytest.mark.parametrize("config_type", [INT, FLOAT, DECIMAL])
def test_bool_is_not_a_number(config_type):
    with pytest.raises(ConfigTypeError, match="not bool"):
        config_type.coerce(True)


def test_a_datetime_is_not_a_date():
    with pytest.raises(ConfigTypeError, match="not datetime"):
        DATE.coerce(datetime(2026, 11, 2, 17, 0))


def test_ints_are_converted_for_float_and_decimal():
    assert FLOAT.coerce(2) == 2.0
    assert isinstance(FLOAT.coerce(2), float)
    assert DECIMAL.coerce(2) == Decimal(2)
    assert isinstance(DECIMAL.coerce(2), Decimal)


def test_matching_values_pass_through():
    assert INT.coerce(5) == 5
    assert DATE.coerce(date(2026, 11, 2)) == date(2026, 11, 2)
    assert JSON.coerce({"a": 1}) == {"a": 1}


def test_mismatches_name_the_expected_type():
    with pytest.raises(ConfigTypeError, match="'int' expects int, not str"):
        INT.coerce("5")
    with pytest.raises(ConfigTypeError, match="expects dict or list, not int"):
        JSON.coerce(5)


def test_to_text_serializes_checked_values():
    assert INT.to_text(5) == "5"
    assert FLOAT.to_text(2) == "2.0"


def test_to_text_turns_serializer_rejections_into_config_value_errors():
    with pytest.raises(ConfigValueError, match="single line"):
        STR.to_text("two\nlines")


def test_from_text_turns_serializer_rejections_into_config_value_errors():
    assert INT.from_text("5") == 5
    with pytest.raises(ConfigValueError, match="whole number"):
        INT.from_text("five")


def test_lists_accept_lists_and_tuples_and_keep_order():
    assert LIST_INT.coerce((3, 1, 2)) == [3, 1, 2]
    assert LIST_INT.to_text([3, 1, 2]) == '["3", "1", "2"]'


def test_lists_reject_other_containers_and_wrong_items():
    with pytest.raises(ConfigTypeError, match="expects a list or tuple, not set"):
        LIST_INT.coerce({1, 2})
    with pytest.raises(ConfigTypeError, match="'int' expects int"):
        LIST_INT.to_text([1, "2"])


def test_sets_accept_lists_sets_and_frozensets():
    assert SET_STR.coerce(["b", "a"]) == frozenset({"a", "b"})
    assert SET_STR.coerce({"a"}) == frozenset({"a"})
    assert SET_STR.to_text(["b", "a"]) == '["b", "a"]'


def test_sets_reject_duplicates_and_other_types():
    with pytest.raises(ConfigValueError, match="Item 3 repeats"):
        SET_STR.coerce(["a", "b", "a"])
    with pytest.raises(ConfigTypeError, match="expects a set, frozenset, list or tuple, not str"):
        SET_STR.coerce("ab")


def test_hashable_follows_the_python_type():
    assert STR.hashable
    assert not JSON.hashable
    assert not ConfigType("thing", "Thing", Unhashable, StrSerializer()).hashable
