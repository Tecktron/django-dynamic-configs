"""A datetime field with a time zone choice, for sites with ``USE_TZ`` on."""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from functools import lru_cache
from typing import Any

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

# Not zones to offer: "localtime" is the server's own zone file, so it means something different on each server, and
# "Factory" is a placeholder with no real offset.
_NOT_ZONES = frozenset({"localtime", "Factory"})


def zone_choices(at: datetime | None = None) -> list[tuple[str, str]]:
    """Return the time zones to choose from, labelled with their UTC offset and ordered by it.

    Zones run from the most negative offset to the most positive, by name within an offset, with UTC first among the
    zones at +0:00. Offsets are the ones in effect at the start of ``at``'s hour, so labels follow daylight saving.

    :param at: an aware datetime whose offsets to show; defaults to now
    :rtype: list[tuple[str, str]]
    """
    at = at or datetime.now(dt_timezone.utc)
    return _zone_choices(at.replace(minute=0, second=0, microsecond=0))


# One hour's list, kept: building it takes about 20 ms, and every datetime form needs it twice.
@lru_cache(maxsize=1)
def _zone_choices(hour: datetime) -> list[tuple[str, str]]:
    offsets = {
        # A ZoneInfo always has an offset; the fallback only satisfies the type.
        zone: hour.astimezone(zoneinfo.ZoneInfo(zone)).utcoffset() or timedelta(0)
        for zone in zoneinfo.available_timezones() - _NOT_ZONES
    }
    zones = sorted(offsets, key=lambda zone: (offsets[zone], zone != "UTC", zone))
    return [(zone, f"{zone} ({_offset_label(offsets[zone])})") for zone in zones]


def _offset_label(offset: timedelta) -> str:
    """Return ``offset`` as ``+5:30`` or ``-5:00``."""
    total = int(offset.total_seconds()) // 60
    hours, minutes = divmod(abs(total), 60)
    return f"{'-' if total < 0 else '+'}{hours}:{minutes:02d}"


class ZonedDateTimeWidget(forms.MultiWidget):
    """A date input, a time input and a time zone select; subclasses swap in other date and time widgets."""

    date_widget: type[forms.Widget] = forms.DateInput
    time_widget: type[forms.Widget] = forms.TimeInput

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Label each part, since the three share the field's one label."""
        widgets = (
            self.date_widget(attrs={**(attrs or {}), "aria-label": "Date"}),
            self.time_widget(attrs={**(attrs or {}), "aria-label": "Time"}),
            # Marked so the admin script can find it and start an empty value on the browser's zone.
            forms.Select(attrs={"aria-label": "Time zone", "data-dynamic-configs-zone": True}, choices=zone_choices()),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value: datetime | None) -> list[Any]:
        """Show ``value`` in the current time zone, which is also the zone the select starts on.

        UTC stands in when the select doesn't offer the current zone, or the value can't be moved into it.
        """
        zone = timezone.get_current_timezone_name()
        if zone not in {name for name, _ in zone_choices()}:
            # A fixed offset (as per-user offset middleware activates) isn't a choice: nothing would be selected, the
            # browser would submit UTC, and saving untouched would move the value.
            zone = "UTC"
        if value is None:
            return [None, None, zone]
        try:
            local = value.astimezone(zoneinfo.ZoneInfo(zone))
        except OverflowError:
            # Too near the ends of the calendar to move into the zone (9999-12-31 east of UTC, say); UTC keeps it.
            local, zone = value.astimezone(dt_timezone.utc), "UTC"
        return [local.date(), local.time(), zone]


class ZonedDateTimeField(forms.MultiValueField):
    """A datetime entered as a date, a time and a time zone; cleans to an aware datetime in that zone, or None."""

    widget = ZonedDateTimeWidget
    default_error_messages = {
        # Django's own messages, so they're translated.
        "invalid_date": forms.SplitDateTimeField.default_error_messages["invalid_date"],
        "invalid_time": forms.SplitDateTimeField.default_error_messages["invalid_time"],
        "invalid_zone": "Choose a time zone.",
        "ambiguous": (
            "%(datetime)s couldn't be interpreted in time zone %(zone)s; it may be ambiguous or it may not exist."
        ),
    }

    def __init__(self, **kwargs: Any) -> None:
        """Build the field from a date, a time and a zone."""
        fields = (forms.DateField(), forms.TimeField(), forms.ChoiceField(choices=zone_choices()))
        super().__init__(fields, **kwargs)

    def compress(self, data_list: list[Any]) -> datetime | None:
        """Return the datetime in the chosen zone; None when there's no date and no time.

        :raises ValidationError: only one of the date and time is given, there's no zone, or the time is skipped or
            repeated by a daylight-saving change in that zone
        """
        if not data_list:
            return None
        day: date | None
        clock: time | None
        day, clock, zone = data_list
        if day is None and clock is None:
            # The select always sends a zone, so an empty value still has one.
            return None
        if day is None:
            raise ValidationError(self.error_messages["invalid_date"], code="invalid_date")
        if clock is None:
            raise ValidationError(self.error_messages["invalid_time"], code="invalid_time")
        if not zone:
            raise ValidationError(self.error_messages["invalid_zone"], code="invalid_zone")
        value = datetime.combine(day, clock, tzinfo=zoneinfo.ZoneInfo(zone))
        # A skipped or repeated wall time has two readings (fold 0 and 1) with different offsets. The admin typed it,
        # so ask rather than guess.
        if value.utcoffset() != value.replace(fold=1).utcoffset():
            raise ValidationError(
                self.error_messages["ambiguous"],
                code="ambiguous",
                params={"datetime": value.replace(tzinfo=None), "zone": zone},
            )
        return value


def datetime_field(**kwargs: Any) -> forms.Field:
    """Return the field for a datetime: with a time zone choice when ``USE_TZ`` is on.

    The field sets its own help, describing the picker: the type's ``help_text`` describes the typed format, which
    still applies to list items and text. With ``USE_TZ`` off there's no zone to choose, so the help says which zone
    times are in.

    :param kwargs: options for the field, such as ``required`` and ``label``; any ``help_text`` is replaced
    :rtype: forms.Field
    """
    if settings.USE_TZ:
        kwargs["help_text"] = "A date, a time and the time zone they're in."
        return ZonedDateTimeField(**kwargs)
    kwargs["help_text"] = f"A date and a time. Times are in the server's time zone ({settings.TIME_ZONE})."
    return forms.SplitDateTimeField(**kwargs)
