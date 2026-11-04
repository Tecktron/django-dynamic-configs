from datetime import date, datetime, time
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

import pytest
from django import forms
from django.utils import timezone

from dynamic_configs.forms.datetime import ZonedDateTimeField, ZonedDateTimeWidget, datetime_field, zone_choices


def clean(*values):
    return ZonedDateTimeField(required=False).clean(list(values))


def messages(*values):
    with pytest.raises(forms.ValidationError) as error:
        clean(*values)
    return error.value.messages


def test_zone_choices_start_with_utc_then_every_zone_by_name():
    choices = zone_choices()
    assert choices[0] == ("UTC", "UTC")
    names = [name for name, _ in choices[1:]]
    assert names == sorted(names)
    assert "America/New_York" in names
    assert "UTC" not in names


def test_cleans_to_an_aware_datetime_in_the_chosen_zone():
    value = clean("2026-11-03", "09:30", "Asia/Tokyo")
    assert value == datetime(2026, 11, 3, 9, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert value.utcoffset().total_seconds() == 9 * 3600


@pytest.mark.parametrize("zone", ["Asia/Tokyo", ""])
def test_no_date_and_no_time_is_empty_whatever_the_zone(zone):
    assert clean("", "", zone) is None


@pytest.mark.parametrize(
    ("day", "clock", "message"),
    [("", "09:30", "Enter a valid date."), ("2026-11-03", "", "Enter a valid time.")],
)
def test_a_date_or_a_time_on_its_own_is_an_error(day, clock, message):
    assert messages(day, clock, "UTC") == [message]


def test_a_missing_zone_is_an_error():
    assert messages("2026-11-03", "09:30", "") == ["Choose a time zone."]


def test_an_unknown_zone_is_an_error():
    assert messages("2026-11-03", "09:30", "Mars/Olympus") == [
        "Select a valid choice. Mars/Olympus is not one of the available choices."
    ]


@pytest.mark.parametrize(
    ("day", "clock"),
    [("2026-03-08", "02:30"), ("2026-11-01", "01:30")],  # skipped (spring forward), repeated (fall back)
)
def test_a_time_a_daylight_saving_change_skips_or_repeats_is_an_error(day, clock):
    # Review focus: the admin typed this time, so it's an error rather than silently shifted.
    assert messages(day, clock, "America/New_York") == [
        f"{day} {clock}:00 couldn't be interpreted in time zone America/New_York; "
        "it may be ambiguous or it may not exist."
    ]


def test_the_widget_shows_a_value_in_the_current_zone():
    widget = ZonedDateTimeWidget()
    value = datetime(2026, 11, 2, 22, 0, tzinfo=dt_timezone.utc)
    assert widget.decompress(value) == [date(2026, 11, 2), time(17, 0), "America/New_York"]
    with timezone.override("Asia/Tokyo"):
        assert widget.decompress(value) == [date(2026, 11, 3), time(7, 0), "Asia/Tokyo"]


def test_the_widget_starts_an_empty_value_on_the_current_zone():
    assert ZonedDateTimeWidget().decompress(None) == [None, None, "America/New_York"]


def test_the_widget_labels_its_inputs_and_marks_the_zone_select():
    html = ZonedDateTimeWidget().render("value", None)
    assert 'aria-label="Date"' in html
    assert 'aria-label="Time"' in html
    assert 'aria-label="Time zone"' in html
    assert "data-dynamic-configs-zone" in html
    assert '<option value="America/New_York" selected>' in html


def test_with_use_tz_on_datetimes_get_the_zoned_field_with_help_for_it():
    # The type's help describes the typed format; next to a picker it would mislead.
    field = datetime_field(help_text="A date and time as YYYY-MM-DD HH:MM.")
    assert type(field) is ZonedDateTimeField
    assert field.help_text == "A date, a time and the time zone they're in."


def test_with_use_tz_off_the_help_says_which_zone(settings):
    settings.USE_TZ = False
    field = datetime_field(help_text="A date and time as YYYY-MM-DD HH:MM.")
    assert type(field) is forms.SplitDateTimeField
    assert field.help_text == "A date and a time. Times are in the server's time zone (America/New_York)."
