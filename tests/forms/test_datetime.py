import re
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


WINTER = datetime(2026, 1, 15, 12, tzinfo=dt_timezone.utc)
SUMMER = datetime(2026, 7, 1, 12, tzinfo=dt_timezone.utc)


def offset_minutes(label):
    sign, hours, minutes = re.search(r"\(([+-])(\d+):(\d\d)\)$", label).groups()
    return (-1 if sign == "-" else 1) * (int(hours) * 60 + int(minutes))


# Zones without daylight saving, so their labels don't depend on today's date.
@pytest.mark.parametrize(
    ("zone", "label"),
    [
        ("UTC", "UTC (+0:00)"),
        ("Asia/Tokyo", "Asia/Tokyo (+9:00)"),
        ("Asia/Kolkata", "Asia/Kolkata (+5:30)"),
        ("Pacific/Marquesas", "Pacific/Marquesas (-9:30)"),
        ("Etc/GMT+12", "Etc/GMT+12 (-12:00)"),
        ("Pacific/Kiritimati", "Pacific/Kiritimati (+14:00)"),
    ],
)
def test_zones_are_labelled_with_their_utc_offset(zone, label):
    assert dict(zone_choices())[zone] == label


def test_zones_run_from_the_most_negative_offset_to_the_most_positive_with_utc_first_at_zero():
    keys = [(offset_minutes(label), name) for name, label in zone_choices(WINTER)]
    assert keys == sorted(keys, key=lambda key: (key[0], key[1] != "UTC", key[1]))
    assert keys[0][0] < 0 < keys[-1][0]
    assert "America/New_York" in [name for _, name in keys]


@pytest.mark.parametrize(("at", "label"), [(WINTER, "America/New_York (-5:00)"), (SUMMER, "America/New_York (-4:00)")])
def test_labels_follow_daylight_saving(at, label):
    assert dict(zone_choices(at))["America/New_York"] == label


def test_the_list_is_for_the_current_hour_and_reused_within_it():
    assert zone_choices() == zone_choices(datetime.now(dt_timezone.utc))
    assert zone_choices(WINTER) is zone_choices(WINTER.replace(minute=59))


@pytest.mark.parametrize("zone", ["localtime", "Factory"])
def test_placeholder_zones_are_not_offered(zone):
    # "localtime" is the server's own zone file, so it means something different on each server; "Factory" has no
    # real offset.
    assert zone not in dict(zone_choices())
    assert messages("2026-11-03", "09:30", zone) == [
        f"Select a valid choice. {zone} is not one of the available choices."
    ]


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


@pytest.mark.parametrize(
    ("value", "zone"),
    [
        # Moving these into the zone would leave the calendar (past 9999 or before year 1).
        (datetime.max.replace(tzinfo=dt_timezone.utc), "Asia/Tokyo"),
        (datetime.min.replace(tzinfo=dt_timezone.utc), "America/New_York"),
    ],
)
def test_a_value_at_the_ends_of_the_calendar_is_shown_in_utc(value, zone):
    with timezone.override(zone):
        assert ZonedDateTimeWidget().decompress(value) == [value.date(), value.time(), "UTC"]


def test_a_current_zone_the_select_doesnt_offer_shows_utc():
    # Review: a fixed offset (as per-user offset middleware activates) isn't a choice, so nothing was selected and the
    # browser submitted UTC, moving a value nobody edited.
    value = datetime(2026, 11, 2, 22, 0, tzinfo=dt_timezone.utc)
    with timezone.override(timezone.get_fixed_timezone(120)):
        assert ZonedDateTimeWidget().decompress(value) == [date(2026, 11, 2), time(22, 0), "UTC"]
        assert ZonedDateTimeWidget().decompress(None) == [None, None, "UTC"]


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
