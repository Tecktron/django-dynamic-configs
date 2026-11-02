"""Built-in serializers.

Each serializer turns a value into the text stored in the database (``serialize``) and back (``deserialize``), and
raises ``ValueError`` when a value or text isn't allowed. Error messages are written for admins, who see them as form
errors, and never include the value itself.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.utils import timezone

_INT_RE = re.compile(r"-?\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# HH:MM with optional seconds; fractions of 3 or 6 digits (all Python 3.10 accepts); optional Z or ±HH:MM offset.
_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{3}(\d{3})?)?)?(Z|[+-]\d{2}:\d{2})?")
_PLAIN_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")
_TRUE_WORDS = frozenset({"true", "1", "yes", "on"})
_FALSE_WORDS = frozenset({"false", "0", "no", "off"})


def format_number(number: float) -> str:
    """Return ``number`` as text, without a trailing ``.0`` for whole numbers."""
    return str(int(number)) if number.is_integer() else repr(number)


def _require_finite(number: float | Decimal) -> None:
    """Raise ValueError for NaN and infinity, which can't be meaningful settings."""
    finite = number.is_finite() if isinstance(number, Decimal) else math.isfinite(number)
    if not finite:
        raise ValueError("A number must be finite (not NaN or infinity).")


class StrSerializer:
    """A single line of text, stored as is."""

    def serialize(self, value: str) -> str:
        """Return ``value``, which must not contain a line break."""
        if "\n" in value or "\r" in value:
            raise ValueError("A string setting must be a single line; use the Text type for several lines.")
        return value

    def deserialize(self, text: str) -> str:
        """Return ``text``, which must not contain a line break."""
        return self.serialize(text)


class TextSerializer:
    """Text that may span several lines, stored as is."""

    def serialize(self, value: str) -> str:
        """Return ``value`` unchanged."""
        return value

    def deserialize(self, text: str) -> str:
        """Return ``text`` unchanged."""
        return text


class IntSerializer:
    """A whole number. Parsing is strict: no decimal point, sign prefix ``+`` or digit separators."""

    def serialize(self, value: int) -> str:
        """Return ``value`` in decimal digits."""
        return str(value)

    def deserialize(self, text: str) -> int:
        """Return the whole number written in ``text``."""
        stripped = text.strip()
        if not _INT_RE.fullmatch(stripped):
            raise ValueError("Enter a whole number, such as 42.")
        return int(stripped)


class FloatSerializer:
    """A finite floating-point number, stored with ``repr`` so it round-trips exactly."""

    def serialize(self, value: float) -> str:
        """Return ``value`` as text."""
        _require_finite(value)
        return repr(value)

    def deserialize(self, text: str) -> float:
        """Return the number written in ``text``."""
        try:
            number = float(text)
        except ValueError:
            raise ValueError("Enter a number, such as 0.5.") from None
        _require_finite(number)
        return number


class DecimalSerializer:
    """A finite decimal number, stored exactly as written (``19.990`` keeps its trailing zero)."""

    def serialize(self, value: Decimal) -> str:
        """Return ``value`` as text."""
        _require_finite(value)
        return str(value)

    def deserialize(self, text: str) -> Decimal:
        """Return the decimal number written in ``text``."""
        try:
            number = Decimal(text.strip())
        except InvalidOperation:
            raise ValueError("Enter a decimal number, such as 19.99.") from None
        _require_finite(number)
        return number


class BoolSerializer:
    """A boolean, stored as ``true`` or ``false``; parsing also accepts yes/no, on/off and 1/0 in any case."""

    def serialize(self, value: bool) -> str:
        """Return ``"true"`` or ``"false"``."""
        return "true" if value else "false"

    def deserialize(self, text: str) -> bool:
        """Return the boolean written in ``text``."""
        word = text.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
        raise ValueError("Enter true or false (yes/no, on/off and 1/0 also work).")


class DateSerializer:
    """A date, stored as ISO 8601 (``YYYY-MM-DD``)."""

    def serialize(self, value: date) -> str:
        """Return ``value`` as ``YYYY-MM-DD``."""
        return value.isoformat()

    def deserialize(self, text: str) -> date:
        """Return the date written in ``text`` as ``YYYY-MM-DD``."""
        # Check the shape first: newer Pythons' fromisoformat also accepts forms such as 20261102, and the accepted
        # input shouldn't depend on the Python version.
        stripped = text.strip()
        if not _DATE_RE.fullmatch(stripped):
            raise ValueError("Enter a date as YYYY-MM-DD.")
        try:
            return date.fromisoformat(stripped)
        except ValueError:
            raise ValueError("Enter a real date, such as 2026-11-02.") from None


def normalize_datetime(value: datetime) -> datetime:
    """Apply Django's time zone settings to ``value``.

    With ``USE_TZ`` on, a naive datetime is read in ``TIME_ZONE`` (ambiguous or missing local times around a daylight
    saving change follow ``zoneinfo``'s ``fold=0`` rule) and the result is converted to UTC. With ``USE_TZ`` off, an
    aware datetime is converted to ``TIME_ZONE`` and made naive, Django's own convention for that mode.

    :param value: a naive or aware datetime
    :returns: an aware UTC datetime (``USE_TZ`` on) or a naive datetime in ``TIME_ZONE`` (``USE_TZ`` off)
    :rtype: datetime
    """
    site_zone = timezone.get_default_timezone()
    if settings.USE_TZ:
        if timezone.is_naive(value):
            value = timezone.make_aware(value, site_zone)
        return value.astimezone(dt_timezone.utc)
    if timezone.is_aware(value):
        value = timezone.make_naive(value, site_zone)
    return value


class DateTimeSerializer:
    """A date and time, stored as ISO 8601 after ``normalize_datetime`` (in UTC when ``USE_TZ`` is on)."""

    def serialize(self, value: datetime) -> str:
        """Return ``value`` normalized and in ISO 8601."""
        return normalize_datetime(value).isoformat()

    def deserialize(self, text: str) -> datetime:
        """Return the datetime written in ``text``, normalized; a missing offset means the site's time zone."""
        stripped = text.strip()
        if not _DATETIME_RE.fullmatch(stripped):
            raise ValueError("Enter a date and time as YYYY-MM-DD HH:MM, optionally with seconds and a UTC offset.")
        if stripped.endswith("Z"):
            # Python 3.10's fromisoformat doesn't accept "Z".
            stripped = stripped[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(stripped)
        except ValueError:
            raise ValueError("Enter a real date and time.") from None
        return normalize_datetime(value)


class DurationSerializer:
    """Base for per-unit durations, stored as a plain number of ``unit`` (a ``timedelta`` keyword)."""

    unit: str

    def serialize(self, value: timedelta) -> str:
        """Return ``value`` as a number of this serializer's unit."""
        return format_number(value / timedelta(**{self.unit: 1}))

    def deserialize(self, text: str) -> timedelta:
        """Return a timedelta of the number of units written in ``text``."""
        stripped = text.strip()
        if not _PLAIN_NUMBER_RE.fullmatch(stripped):
            raise ValueError(f"Enter a number of {self.unit}, such as 1.5.")
        try:
            return timedelta(**{self.unit: float(stripped)})
        except OverflowError:
            raise ValueError(f"That many {self.unit} is too large.") from None


class SecondsSerializer(DurationSerializer):
    """A duration stored as a number of seconds."""

    unit = "seconds"


class MinutesSerializer(DurationSerializer):
    """A duration stored as a number of minutes."""

    unit = "minutes"


class HoursSerializer(DurationSerializer):
    """A duration stored as a number of hours."""

    unit = "hours"


class DaysSerializer(DurationSerializer):
    """A duration stored as a number of days."""

    unit = "days"


class WeeksSerializer(DurationSerializer):
    """A duration stored as a number of weeks."""

    unit = "weeks"


def _reject_json_constant(name: str) -> Any:
    """Refuse NaN and Infinity, which ``json.loads`` would otherwise accept."""
    raise ValueError(f"JSON can't contain {name}.")


class JSONSerializer:
    """A JSON object or array."""

    def serialize(self, value: dict[str, Any] | list[Any]) -> str:
        """Return ``value`` as JSON text."""
        try:
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(f"The value can't be stored as JSON: {error}") from error

    def deserialize(self, text: str) -> dict[str, Any] | list[Any]:
        """Return the object or array written in ``text``."""
        try:
            value = json.loads(text, parse_constant=_reject_json_constant)
        except ValueError:
            raise ValueError("Enter valid JSON.") from None
        if not isinstance(value, (dict, list)):
            raise ValueError("Enter a JSON object or array.")
        return value


class ListSerializer:
    """A list, stored as a JSON array of each item's text (from the item type's serializer)."""

    def __init__(self, item_serializer: Any) -> None:
        """Use ``item_serializer`` for each item."""
        self.item_serializer = item_serializer

    def serialize(self, value: list[Any]) -> str:
        """Return the items, in order, as a JSON array of their text."""
        return json.dumps([self.item_serializer.serialize(item) for item in value], ensure_ascii=False)

    def deserialize(self, text: str) -> list[Any]:
        """Return the items stored in ``text``, in order."""
        try:
            raw = json.loads(text)
        except ValueError:
            raise ValueError("A list must be stored as a JSON array.") from None
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ValueError("A list must be stored as a JSON array of strings.")
        return [self.item_serializer.deserialize(item) for item in raw]


class SetSerializer(ListSerializer):
    """A set, stored like a list (in the order entered) and read back as a ``frozenset``."""

    def deserialize(self, text: str) -> frozenset[Any]:  # type: ignore[override]
        """Return the items stored in ``text`` as a frozenset, rejecting duplicates."""
        items = super().deserialize(text)
        result = frozenset(items)
        if len(result) != len(items):
            raise ValueError("A set can't contain the same item twice.")
        return result
