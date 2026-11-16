"""Every built-in type reads back what it wrote: ``from_text(to_text(value)) == value`` for edge values.

A case a later task fixes is marked ``xfail(strict=True)`` with the task named, so fixing it turns the mark into a
failure that says to remove it.
"""

import sys
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest

from dynamic_configs.types.registry import get_registry

UTC = dt_timezone.utc
LONG_TEXT = "long text, " * 2000
NON_ASCII = "héllo ☃ 日本語 😀"


def task_3(value, reason):
    """Mark a case that Task 3 fixes."""
    return pytest.param(value, id=reason, marks=pytest.mark.xfail(strict=True, reason=f"Task 3: {reason}"))


def check_round_trip(key, value):
    config_type = get_registry().get(key)
    assert config_type.from_text(config_type.to_text(value)) == value


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("a", id="one-character"),
        pytest.param(LONG_TEXT, id="long-text"),
        pytest.param(NON_ASCII, id="non-ascii"),
        pytest.param("  padded  ", id="leading-and-trailing-spaces"),
        pytest.param("a\ttab", id="tab"),
    ],
)
def test_str(value):
    check_round_trip("str", value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("one\ntwo\r\nthree\n", id="line-breaks"),
        pytest.param(LONG_TEXT, id="long-text"),
        pytest.param(NON_ASCII, id="non-ascii"),
    ],
)
def test_text(value):
    check_round_trip("text", value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(2**63 - 1, id="int64-max"),
        pytest.param(-(2**63), id="int64-min"),
        pytest.param(sys.maxsize**3, id="beyond-64-bits"),
    ],
)
def test_int(value):
    check_round_trip("int", value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(0.0, id="zero"),
        pytest.param(-0.0, id="negative-zero"),
        pytest.param(1.5, id="fraction"),
        pytest.param(-1.5, id="negative"),
        pytest.param(0.1 + 0.2, id="binary-rounding"),
        pytest.param(sys.float_info.max, id="max"),
        pytest.param(-sys.float_info.max, id="min"),
        pytest.param(sys.float_info.min, id="smallest-normal"),
        pytest.param(5e-324, id="smallest-subnormal"),
        pytest.param(1e22, id="exponent-notation"),
    ],
)
def test_float(value):
    check_round_trip("float", value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(Decimal("0"), id="zero"),
        pytest.param(Decimal("-19.990"), id="negative-trailing-zero"),
        pytest.param(Decimal("9" * 100), id="many-digits"),
        pytest.param(Decimal("1E-100"), id="tiny"),
        pytest.param(Decimal("1E+100"), id="huge"),
    ],
)
def test_decimal(value):
    check_round_trip("decimal", value)


@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
def test_bool(value):
    check_round_trip("bool", value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(date.min, id="min"),
        pytest.param(date.max, id="max"),
        pytest.param(date(2024, 2, 29), id="leap-day"),
    ],
)
def test_date(value):
    check_round_trip("date", value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(datetime.min.replace(tzinfo=UTC), id="min"),
        pytest.param(datetime.max.replace(tzinfo=UTC), id="max-with-microseconds"),
        pytest.param(datetime(2026, 11, 1, 5, 30, tzinfo=UTC), id="across-a-fall-back-fold"),
        pytest.param(datetime(2026, 3, 8, 7, 30, 15, 500, tzinfo=UTC), id="across-a-spring-forward-gap"),
        pytest.param(datetime(2026, 6, 1, 12, 0, tzinfo=dt_timezone(timedelta(hours=5, minutes=30))), id="offset"),
    ],
)
def test_datetime(value):
    check_round_trip("datetime", value)


DURATION_KEYS = ["seconds", "minutes", "hours", "days", "weeks"]


@pytest.mark.parametrize("key", DURATION_KEYS)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(timedelta(0), id="zero"),
        pytest.param(timedelta(seconds=-90), id="negative"),
        pytest.param(timedelta(days=3, seconds=1), id="whole-and-fraction"),
        pytest.param(timedelta(weeks=52 * 100), id="a-century"),
        pytest.param(timedelta(microseconds=1), id="one-microsecond"),
    ],
)
def test_durations(key, value):
    check_round_trip(key, value)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        pytest.param(
            key, timedelta.max, id=f"timedelta-max-{key}", marks=pytest.mark.xfail(strict=True, reason="Task 3")
        )
        for key in DURATION_KEYS
    ]
    + [pytest.param(key, timedelta.min, id=f"timedelta-min-{key}") for key in DURATION_KEYS[:-1]]
    + [
        pytest.param(
            "weeks", timedelta.min, id="timedelta-min-weeks", marks=pytest.mark.xfail(strict=True, reason="Task 3")
        )
    ],
)
def test_duration_extremes(key, value):
    check_round_trip(key, value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({}, id="empty-object"),
        pytest.param([], id="empty-array"),
        pytest.param({"a": [1, 2.5, None, True, {"b": "c"}]}, id="nested"),
        pytest.param({"text": NON_ASCII}, id="non-ascii"),
        pytest.param([LONG_TEXT], id="long-text"),
        pytest.param([2**63, -(2**63) - 1], id="ints-beyond-64-bits"),
        task_3({1: "a"}, "non-string-key"),
        task_3([10**5000], "huge-int"),
        task_3([1e400], "float-overflowing-to-infinity"),
    ],
)
def test_json(value):
    check_round_trip("json", value)


LISTS = [
    pytest.param("list:str", [], id="str-empty"),
    pytest.param("list:str", ["", "a", NON_ASCII, "dup", "dup"], id="str-with-repeats-and-empty-items"),
    pytest.param("list:text", ["one\ntwo", ""], id="text-line-breaks"),
    pytest.param("list:int", [0, -1, 2**63 - 1, -(2**63)], id="int-extremes"),
    pytest.param("list:float", [0.0, sys.float_info.max, 5e-324], id="float-extremes"),
    pytest.param("list:decimal", [Decimal("0"), Decimal("-19.990")], id="decimal"),
    pytest.param("list:bool", [True, False, True], id="bool-with-repeats"),
    pytest.param("list:date", [date.min, date.max], id="date-bounds"),
    pytest.param(
        "list:datetime", [datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC)], id="datetime-bounds"
    ),
    pytest.param("list:seconds", [timedelta(0), timedelta(seconds=-90)], id="seconds"),
    pytest.param("list:weeks", [timedelta(0), timedelta(weeks=3)], id="weeks"),
]


@pytest.mark.parametrize(("key", "value"), LISTS)
def test_lists(key, value):
    check_round_trip(key, value)


SETS = [
    pytest.param("set:str", frozenset(), id="str-empty"),
    pytest.param("set:str", frozenset({"", "a", NON_ASCII}), id="str"),
    pytest.param("set:int", frozenset({0, -1, 2**63 - 1, -(2**63)}), id="int-extremes"),
    pytest.param("set:float", frozenset({0.0, sys.float_info.max, 5e-324}), id="float-extremes"),
    pytest.param("set:decimal", frozenset({Decimal("0"), Decimal("-19.990")}), id="decimal"),
    pytest.param("set:bool", frozenset({True, False}), id="bool"),
    pytest.param("set:date", frozenset({date.min, date.max}), id="date-bounds"),
    pytest.param(
        "set:datetime",
        frozenset({datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC)}),
        id="datetime-bounds",
    ),
    pytest.param("set:seconds", frozenset({timedelta(0), timedelta(seconds=-90)}), id="seconds"),
    pytest.param("set:weeks", frozenset({timedelta(0), timedelta(weeks=3)}), id="weeks"),
]


@pytest.mark.parametrize(("key", "value"), SETS)
def test_sets(key, value):
    check_round_trip(key, value)
