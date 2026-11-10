"""Example custom types: an amount of money, and an amount with a currency built on it.

They are not registered by default; enable them in ``DYNAMIC_CONFIGS["TYPES"]`` (see the documentation). They also
show how to write a custom type and how to extend one: ``MoneyCurrencySerializer`` subclasses ``MoneySerializer`` and
reuses its amount handling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_AMOUNT_RE = re.compile(r"-?\d+(\.\d+)?")
_CURRENCY_RE = re.compile(r"[A-Z]{3}")
_CENTS = Decimal("0.01")


def check_amount(amount: Decimal) -> Decimal:
    """Return ``amount`` with exactly 2 decimal places.

    More than 2 decimal places is rejected, never rounded, and counted as written: ``9.990`` is rejected too.

    :raises ValueError: the amount isn't finite, has more than 2 decimal places, or is too large
    """
    if not amount.is_finite():
        raise ValueError("An amount must be a finite number.")
    if amount.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValueError("An amount can have at most 2 decimal places.")
    try:
        return amount.quantize(_CENTS)
    except InvalidOperation:
        raise ValueError("That amount is too large.") from None


@dataclass(frozen=True)
class Money:
    """An amount (stored with exactly 2 decimal places) and a 3-letter currency code, such as ``9.99 CAD``.

    Frozen, so it's immutable and hashable (and gets a set variant). Invalid values can't be created.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        """Validate both parts and keep the amount with exactly 2 decimal places."""
        if not isinstance(self.amount, Decimal):
            raise ValueError("Money's amount must be a Decimal.")
        if not isinstance(self.currency, str) or not _CURRENCY_RE.fullmatch(self.currency):
            raise ValueError("A currency must be a 3-letter code in capitals, such as CAD.")
        # Frozen dataclass: assign through object to normalize the amount.
        object.__setattr__(self, "amount", check_amount(self.amount))

    def __str__(self) -> str:
        """Return the amount and currency, such as ``9.99 CAD``."""
        return f"{self.amount} {self.currency}"


def by_currency_then_amount(money: Money) -> tuple[str, Decimal]:
    """Return the sort key for ``money_currency`` lists: currency, then amount.

    ``Money`` defines no order, since amounts in different currencies don't compare, so its ``TYPES`` entry names this
    as its ``sort_key`` (the worked example of the key).
    """
    return (money.currency, money.amount)


class MoneySerializer:
    """An amount of money: plain decimal text with at most 2 decimal places, stored with exactly 2 (``10.00``)."""

    def serialize(self, value: Decimal) -> str:
        """Return the amount with exactly 2 decimal places."""
        return str(check_amount(value))

    def deserialize(self, text: str) -> Decimal:
        """Return the amount written in ``text``; exponents, separators and signs other than ``-`` are rejected."""
        stripped = text.strip()
        if not _AMOUNT_RE.fullmatch(stripped):
            raise ValueError("Enter an amount such as 9.99.")
        return check_amount(Decimal(stripped))


class MoneyCurrencySerializer(MoneySerializer):
    """An amount and a currency code, stored as ``9.99 CAD``; reuses ``MoneySerializer`` for the amount."""

    def serialize(self, value: Money) -> str:  # type: ignore[override]
        """Return the amount and currency, such as ``9.99 CAD``."""
        return f"{super().serialize(value.amount)} {value.currency}"

    def deserialize(self, text: str) -> Money:  # type: ignore[override]
        """Return the money written in ``text``; the currency code may be in any case."""
        parts = text.split()
        if len(parts) != 2:
            raise ValueError("Enter an amount and a currency code, such as 9.99 CAD.")
        return Money(super().deserialize(parts[0]), parts[1].upper())
