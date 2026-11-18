"""Example custom types: an amount of money, and an amount with a currency built on it.

They are not registered by default; enable them in ``DYNAMIC_CONFIGS["TYPES"]`` (see the documentation). They also
show how to write a custom type and how to extend one: ``MoneyCurrencySerializer`` subclasses ``MoneySerializer`` and
reuses its amount handling.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_05UP,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

from dynamic_configs.types import iso4217
from dynamic_configs.types.serializers import BaseSerializer

_CENTS = Decimal("0.01")
# Spelled out, not the thread's context: low precision refuses small amounts, and untrapped errors give NaN.
_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation, DivisionByZero, Overflow])


def check_amount(amount: Decimal, rounding: str | None = None) -> Decimal:
    """Return ``amount`` with exactly 2 decimal places.

    Without ``rounding``, more than 2 decimal places is rejected, never rounded, and counted as written: ``9.990`` is
    rejected too. With one of decimal's ``ROUND_*`` constants, the amount is rounded to 2 places that way. A zero,
    including a negative amount that rounds to zero, is returned without a sign (``0.00``, not ``-0.00``).

    :param rounding: how to round an amount with more than 2 places, or None to reject it
    :raises ValueError: the amount isn't finite, has more than 2 decimal places (and ``rounding`` is None), or is too
        large
    """
    if not amount.is_finite():
        raise ValueError("An amount must be a finite number.")
    if rounding is None and amount.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValueError("An amount can have at most 2 decimal places.")
    try:
        with localcontext(_CONTEXT):
            result = amount.quantize(_CENTS, rounding=rounding)
    except InvalidOperation:
        raise ValueError("That amount is too large.") from None
    return result.copy_abs() if result.is_zero() else result


@dataclass(frozen=True)
class Money:
    """An amount (stored with exactly 2 decimal places) and a 3-letter currency code, such as ``9.99 CAD``.

    Frozen, so it's immutable and hashable (and gets a set variant). Invalid values can't be created.
    """

    amount: Decimal
    currency: str

    _CURRENCY_RE = re.compile(r"[A-Z]{3}")

    def __post_init__(self) -> None:
        """Validate both parts and keep the amount with exactly 2 decimal places."""
        if not isinstance(self.amount, Decimal):
            raise ValueError("Money's amount must be a Decimal.")
        if not isinstance(self.currency, str) or not self._CURRENCY_RE.fullmatch(self.currency):
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


class MoneySerializer(BaseSerializer):
    """An amount of money: plain decimal text, stored with exactly 2 decimal places (``10.00``).

    More than 2 places is refused, unless ``rounding`` says how to round it.
    """

    _AMOUNT_RE = re.compile(r"-?\d+(\.\d+)?")
    ROUNDINGS = frozenset(
        {ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_05UP}
    )

    def __init__(self, rounding: str | None = None) -> None:
        """Round amounts with more than 2 places the way ``rounding`` says, or refuse them when it's None.

        :param rounding: None, or one of decimal's ``ROUND_*`` constants (such as ``decimal.ROUND_HALF_UP``)
        :raises ValueError: ``rounding`` is anything else
        """
        super().__init__()
        if rounding is not None and rounding not in self.ROUNDINGS:
            raise ValueError("rounding must be one of decimal's ROUND_* constants.")
        self.rounding = rounding

    def serialize(self, value: Decimal) -> str:
        """Return the amount with exactly 2 decimal places."""
        return str(check_amount(value, self.rounding))

    def deserialize(self, text: str) -> Decimal:
        """Return the amount written in ``text``; exponents, separators and signs other than ``-`` are rejected."""
        stripped = text.strip()
        if not self._AMOUNT_RE.fullmatch(stripped):
            raise ValueError("Enter an amount such as 9.99.")
        return check_amount(Decimal(stripped), self.rounding)


class MoneyCurrencySerializer(MoneySerializer):
    """An amount and a currency code, stored as ``9.99 CAD``; reuses ``MoneySerializer`` for the amount.

    ``currencies`` are the codes the admin suggests for the currency; they are suggestions, never a check.
    """

    # ASCII only: upper-casing "ıso" (a dotless i) would give "ISO".
    _CODE_RE = re.compile(r"[A-Za-z]{3}", re.ASCII)
    _SUGGESTED_RE = re.compile(r"[A-Z]{3}", re.ASCII)

    def __init__(
        self, rounding: str | None = None, currencies: Iterable[str] | Mapping[str, str] | None = None
    ) -> None:
        """Round as ``MoneySerializer`` does, and suggest ``currencies`` in the admin.

        :param rounding: None, or one of decimal's ``ROUND_*`` constants
        :param currencies: None for the ISO 4217 list; a list of codes, labelled from that list when it knows them; a
            mapping of codes to labels, used as given; or empty for no suggestions
        :raises ValueError: ``rounding`` is not valid, or ``currencies`` is a bare string, or has anything but codes
            of 3 capital letters A-Z (with a string for each label, in a mapping)
        """
        super().__init__(rounding)
        self.currencies = dict(iso4217.CURRENCIES) if currencies is None else self._suggestions(currencies)

    @classmethod
    def _suggestions(cls, currencies: Iterable[str] | Mapping[str, str]) -> dict[str, str]:
        """Return ``currencies`` as a dict of code to label, in the order given (sorted, from a set)."""
        message = "currencies must be a list of 3-letter codes in capitals, or a mapping of codes to labels."
        if isinstance(currencies, str) or not isinstance(currencies, Iterable):
            raise ValueError(message)
        codes = list(currencies)
        if not all(isinstance(code, str) and cls._SUGGESTED_RE.fullmatch(code) for code in codes):
            raise ValueError(message)
        if isinstance(currencies, Mapping):
            if not all(isinstance(label, str) for label in currencies.values()):
                raise ValueError(message)
            return dict(currencies)
        if not isinstance(currencies, Sequence):
            # A set has no order of its own, and string hashing differs from one run to the next.
            codes.sort()
        return {code: iso4217.CURRENCIES.get(code, "") for code in codes}

    def serialize(self, value: Money) -> str:  # type: ignore[override]
        """Return the amount and currency, such as ``9.99 CAD``."""
        return f"{super().serialize(value.amount)} {value.currency}"

    def deserialize(self, text: str) -> Money:  # type: ignore[override]
        """Return the money written in ``text``; the currency code may be in any case."""
        parts = text.split()
        if len(parts) != 2:
            raise ValueError("Enter an amount and a currency code, such as 9.99 CAD.")
        if not self._CODE_RE.fullmatch(parts[1]):
            raise ValueError("A currency must be a 3-letter code, such as CAD.")
        return Money(super().deserialize(parts[0]), parts[1].upper())
