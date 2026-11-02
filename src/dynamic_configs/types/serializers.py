"""Built-in serializers.

Each serializer turns a value into the text stored in the database (``serialize``) and back (``deserialize``), and
raises ``ValueError`` when a value or text isn't allowed. Error messages are written for admins, who see them as form
errors, and never include the value itself.
"""

from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

_INT_RE = re.compile(r"-?\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
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
