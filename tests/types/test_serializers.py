from datetime import date
from decimal import Decimal

import pytest

from dynamic_configs.types.serializers import (
    BoolSerializer,
    DateSerializer,
    DecimalSerializer,
    FloatSerializer,
    IntSerializer,
    StrSerializer,
    TextSerializer,
    format_number,
)


@pytest.mark.parametrize(("number", "text"), [(2.0, "2"), (1.5, "1.5"), (-3.0, "-3")])
def test_format_number_drops_a_trailing_point_zero(number, text):
    assert format_number(number) == text


def test_str_round_trips_a_single_line():
    assert StrSerializer().serialize("Example") == "Example"
    assert StrSerializer().deserialize("Example") == "Example"


@pytest.mark.parametrize("text", ["two\nlines", "carriage\rreturn"])
def test_str_rejects_line_breaks(text):
    with pytest.raises(ValueError, match="single line"):
        StrSerializer().serialize(text)
    with pytest.raises(ValueError, match="single line"):
        StrSerializer().deserialize(text)


def test_text_keeps_line_breaks():
    assert TextSerializer().serialize("a\nb") == "a\nb"
    assert TextSerializer().deserialize("a\nb") == "a\nb"


def test_int_round_trips():
    assert IntSerializer().serialize(-42) == "-42"
    assert IntSerializer().deserialize(" -42 ") == -42


@pytest.mark.parametrize("text", ["1.0", "+5", "1_000", "", "four"])
def test_int_parsing_is_strict(text):
    with pytest.raises(ValueError, match="whole number"):
        IntSerializer().deserialize(text)


def test_float_round_trips():
    assert FloatSerializer().serialize(0.1) == "0.1"
    assert FloatSerializer().deserialize("0.1") == 0.1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_float_rejects_non_finite_values(value):
    with pytest.raises(ValueError, match="finite"):
        FloatSerializer().serialize(value)


@pytest.mark.parametrize(("text", "message"), [("nan", "finite"), ("inf", "finite"), ("half", "number")])
def test_float_rejects_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        FloatSerializer().deserialize(text)


def test_decimal_round_trips_exactly():
    assert DecimalSerializer().serialize(Decimal("19.990")) == "19.990"
    assert DecimalSerializer().deserialize("19.990") == Decimal("19.990")


def test_decimal_rejects_non_finite_values():
    with pytest.raises(ValueError, match="finite"):
        DecimalSerializer().serialize(Decimal("NaN"))


@pytest.mark.parametrize(("text", "message"), [("Infinity", "finite"), ("nineteen", "decimal number")])
def test_decimal_rejects_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        DecimalSerializer().deserialize(text)


def test_bool_serializes_as_words():
    assert BoolSerializer().serialize(True) == "true"
    assert BoolSerializer().serialize(False) == "false"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("TRUE", True),
        (" yes ", True),
        ("1", True),
        ("on", True),
        ("false", False),
        ("No", False),
        ("0", False),
        ("off", False),
    ],
)
def test_bool_accepts_common_words(text, expected):
    assert BoolSerializer().deserialize(text) is expected


def test_bool_rejects_anything_else():
    with pytest.raises(ValueError, match="true or false"):
        BoolSerializer().deserialize("maybe")


def test_date_round_trips():
    assert DateSerializer().serialize(date(2026, 11, 2)) == "2026-11-02"
    assert DateSerializer().deserialize(" 2026-11-02 ") == date(2026, 11, 2)


@pytest.mark.parametrize(("text", "message"), [("20261102", "YYYY-MM-DD"), ("2026-02-30", "real date")])
def test_date_rejects_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        DateSerializer().deserialize(text)
