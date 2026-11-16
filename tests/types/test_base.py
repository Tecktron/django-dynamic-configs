from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from enum import Enum

import pytest

from dynamic_configs.exceptions import ConfigTypeError, ConfigValueError
from dynamic_configs.types.base import ConfigType
from dynamic_configs.types.builtin import BUILTIN_TYPES
from dynamic_configs.types.serializers import (
    BaseSerializer,
    DateSerializer,
    DateTimeSerializer,
    DecimalSerializer,
    FloatSerializer,
    IntSerializer,
    JSONSerializer,
    ListSerializer,
    SetSerializer,
    StrSerializer,
)
from tests.custom_types import Color, ColorSerializer, color_hex

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


class CrashingSerializer:
    def serialize(self, value):
        return str(value)

    def deserialize(self, text):
        raise KeyError(text)


def test_any_error_while_reading_stored_text_is_a_config_value_error():
    # Review finding: a custom serializer raising something other than ValueError escaped get's default guarantee.
    crashing = ConfigType("crashing", "Crashing", str, CrashingSerializer())
    with pytest.raises(ConfigValueError, match="KeyError"):
        crashing.from_text("anything")


def test_types_whose_values_define_an_order_are_sortable():
    by_key = {config_type.key: config_type for config_type in BUILTIN_TYPES}
    assert all(by_key[key].sortable for key in ("str", "int", "float", "decimal", "bool", "date", "datetime", "hours"))


def test_a_class_without_an_order_is_sortable_only_with_a_key():
    assert not ConfigType("color", "Color", Color, ColorSerializer()).sortable
    assert ConfigType("color", "Color", Color, ColorSerializer(), sort_key=color_hex).sortable


def test_sort_uses_the_key_or_the_values_and_can_go_backwards():
    plain = ConfigType("int", "Integer", int, IntSerializer())
    assert plain.sort([10, 9, 100]) == [9, 10, 100]
    assert plain.sort([10, 9, 100], descending=True) == [100, 10, 9]
    color = ConfigType("color", "Color", Color, ColorSerializer(), sort_key=color_hex)
    assert color.sort([Color("#bbbbbb"), Color("#aaaaaa")]) == [Color("#aaaaaa"), Color("#bbbbbb")]


def test_sorting_values_without_an_order_raises():
    with pytest.raises(TypeError):
        ConfigType("color", "Color", Color, ColorSerializer()).sort([Color("#bbbbbb"), Color("#aaaaaa")])


class Priority(int, Enum):
    HIGH = 3


class Colour(str, Enum):
    RED = "red"


class OddFloat(float):
    def __repr__(self):
        return "OddFloat(1.5)"


def test_int_subclass_is_stored_as_its_number():
    assert INT.to_text(Priority.HIGH) == "3"


def test_str_subclass_is_stored_as_its_text():
    text = STR.to_text(Colour.RED)
    assert text == "red"
    assert type(text) is str


def test_float_subclass_is_stored_as_its_number():
    assert FLOAT.to_text(OddFloat(1.5)) == "1.5"


def test_float_from_a_huge_int_is_a_config_value_error():
    with pytest.raises(ConfigValueError, match="too large for a float"):
        FLOAT.to_text(10**400)


def test_lone_surrogate_is_refused_before_the_database():
    with pytest.raises(ConfigValueError, match="can't be stored"):
        JSON.to_text({"a": "\ud800"})
    with pytest.raises(ConfigValueError, match="lone surrogate"):
        STR.to_text("\udfff")


def test_a_rule_in_deserialize_holds_on_write():
    class EvenOnly(BaseSerializer):
        def serialize(self, value):
            return str(value)

        def deserialize(self, text):
            if int(text) % 2:
                raise ValueError("Enter an even number.")
            return int(text)

    even = ConfigType("even", "Even", int, EvenOnly())
    assert even.to_text(4) == "4"
    with pytest.raises(ConfigValueError) as error:
        even.to_text(3)
    assert str(error.value) == "The value can't be stored: Enter an even number."


def test_a_read_failure_that_isnt_a_value_error_is_refused_without_the_value():
    class Broken(BaseSerializer):
        def serialize(self, value):
            return "secret"

        def deserialize(self, text):
            raise KeyError(text)

    with pytest.raises(ConfigValueError) as error:
        ConfigType("broken", "Broken", int, Broken()).to_text(1)
    assert str(error.value) == "The value can't be stored: Reading the stored text failed with KeyError."


def test_set_items_equal_once_read_back_are_refused(settings):
    # With USE_TZ off, 01:30 EDT and 01:30 EST (an hour apart) are the same local time once stored.
    settings.USE_TZ = False
    set_datetime = ConfigType(
        "set:datetime",
        "Set of Date and time",
        frozenset,
        SetSerializer(DateTimeSerializer()),
        item_type=ConfigType("datetime", "Date and time", datetime, DateTimeSerializer()),
        container="set",
    )
    first = datetime(2026, 11, 1, 5, 30, tzinfo=dt_timezone.utc)
    second = datetime(2026, 11, 1, 6, 30, tzinfo=dt_timezone.utc)
    with pytest.raises(ConfigValueError, match="The value can't be stored: A set can't contain the same item twice."):
        set_datetime.to_text({first, second})
