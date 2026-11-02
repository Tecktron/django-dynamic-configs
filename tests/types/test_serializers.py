from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest

from dynamic_configs.types.serializers import (
    BoolSerializer,
    DateSerializer,
    DateTimeSerializer,
    DaysSerializer,
    DecimalSerializer,
    FloatSerializer,
    HoursSerializer,
    IntSerializer,
    JSONSerializer,
    ListSerializer,
    MinutesSerializer,
    SecondsSerializer,
    SetSerializer,
    StrSerializer,
    TextSerializer,
    WeeksSerializer,
    format_number,
    normalize_datetime,
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


UTC = dt_timezone.utc


def test_naive_datetimes_are_read_in_the_site_time_zone():
    # 17:00 in New York on 2026-11-02 is EST (UTC-5), so 22:00 UTC.
    assert normalize_datetime(datetime(2026, 11, 2, 17, 0)) == datetime(2026, 11, 2, 22, 0, tzinfo=UTC)


def test_aware_datetimes_keep_their_instant_and_become_utc():
    value = datetime(2026, 11, 2, 17, 0, tzinfo=dt_timezone(timedelta(hours=1)))
    normalized = normalize_datetime(value)
    assert normalized == value
    assert normalized.tzinfo is UTC


def test_without_use_tz_aware_datetimes_become_naive_site_time(settings):
    settings.USE_TZ = False
    assert normalize_datetime(datetime(2026, 11, 2, 22, 0, tzinfo=UTC)) == datetime(2026, 11, 2, 17, 0)


def test_without_use_tz_naive_datetimes_stay_as_they_are(settings):
    settings.USE_TZ = False
    assert normalize_datetime(datetime(2026, 11, 2, 17, 0)) == datetime(2026, 11, 2, 17, 0)


def test_datetimes_are_stored_in_utc():
    assert DateTimeSerializer().serialize(datetime(2026, 11, 2, 17, 0)) == "2026-11-02T22:00:00+00:00"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-02 17:00", datetime(2026, 11, 2, 22, 0, tzinfo=UTC)),
        ("2026-11-02T17:00:30", datetime(2026, 11, 2, 22, 0, 30, tzinfo=UTC)),
        ("2026-11-02T22:00:00Z", datetime(2026, 11, 2, 22, 0, tzinfo=UTC)),
        ("2026-11-02T22:00:00.250+00:00", datetime(2026, 11, 2, 22, 0, 0, 250000, tzinfo=UTC)),
    ],
)
def test_datetime_text_with_or_without_a_zone(text, expected):
    assert DateTimeSerializer().deserialize(text) == expected


def test_an_ambiguous_local_time_resolves_to_its_first_occurrence():
    # Daylight saving ends in New York at 02:00 on 2026-11-01, so 01:30 happens twice; fold=0 picks the first
    # (EDT, UTC-4), which is 05:30 UTC.
    assert DateTimeSerializer().deserialize("2026-11-01 01:30") == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)


@pytest.mark.parametrize(("text", "message"), [("2026-11-02", "YYYY-MM-DD HH:MM"), ("2026-02-30 10:00", "real date")])
def test_datetime_rejects_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        DateTimeSerializer().deserialize(text)


@pytest.mark.parametrize(
    ("serializer", "value", "text"),
    [
        (SecondsSerializer(), timedelta(seconds=90), "90"),
        (MinutesSerializer(), timedelta(minutes=1.5), "1.5"),
        (HoursSerializer(), timedelta(hours=1.5), "1.5"),
        (DaysSerializer(), timedelta(days=2), "2"),
        (WeeksSerializer(), timedelta(weeks=-1), "-1"),
    ],
)
def test_durations_round_trip_in_their_unit(serializer, value, text):
    assert serializer.serialize(value) == text
    assert serializer.deserialize(f" {text} ") == value


@pytest.mark.parametrize("text", ["1e3", "1h", "", "inf"])
def test_durations_reject_anything_but_a_plain_number(text):
    with pytest.raises(ValueError, match="number of hours"):
        HoursSerializer().deserialize(text)


def test_durations_reject_values_too_large_for_timedelta():
    with pytest.raises(ValueError, match="too large"):
        WeeksSerializer().deserialize("9" * 20)


def test_json_round_trips_objects_and_arrays():
    assert JSONSerializer().serialize({"name": "Café", "sizes": [1, 2]}) == '{"name": "Café", "sizes": [1, 2]}'
    assert JSONSerializer().deserialize("[1, 2]") == [1, 2]


@pytest.mark.parametrize("value", [{"when": date(2026, 11, 2)}, {"ratio": float("nan")}])
def test_json_rejects_values_json_cannot_hold(value):
    with pytest.raises(ValueError, match="stored as JSON"):
        JSONSerializer().serialize(value)


@pytest.mark.parametrize(("text", "message"), [("{", "valid JSON"), ("[NaN]", "valid JSON"), ("5", "object or array")])
def test_json_rejects_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        JSONSerializer().deserialize(text)


def test_lists_store_each_item_as_text_in_order():
    serializer = ListSerializer(IntSerializer())
    assert serializer.serialize([3, 1, 2]) == '["3", "1", "2"]'
    assert serializer.deserialize('["3", "1", "2"]') == [3, 1, 2]


@pytest.mark.parametrize(
    ("text", "message"), [("[", "JSON array"), ('{"a": "1"}', "array of strings"), ("[1]", "array of strings")]
)
def test_lists_reject_bad_text(text, message):
    with pytest.raises(ValueError, match=message):
        ListSerializer(IntSerializer()).deserialize(text)


def test_list_items_are_validated_by_the_item_serializer():
    with pytest.raises(ValueError, match="whole number"):
        ListSerializer(IntSerializer()).deserialize('["1", "one"]')


def test_sets_deserialize_to_frozensets():
    assert SetSerializer(StrSerializer()).deserialize('["b", "a"]') == frozenset({"a", "b"})


def test_sets_reject_duplicates_after_parsing():
    # "1" and "01" are different text but the same integer.
    with pytest.raises(ValueError, match="same item twice"):
        SetSerializer(IntSerializer()).deserialize('["1", "01"]')
