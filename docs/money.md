# Worked example: the money types

Two working custom types ship with the package, as the reference example of writing a type and then extending one:
`money`, an amount, and `money_currency`, an amount and a currency built on it. The code below is the package's own
(`dynamic_configs/types/money.py` and `dynamic_configs/forms/money.py`).

They are **not registered by default**. Enable either or both through `TYPES`, exactly as you would your own types:

```python
DYNAMIC_CONFIGS = {
    "TYPES": {
        "money": {
            "type": "decimal.Decimal",
            "serializer": "dynamic_configs.types.money.MoneySerializer",
            "form": "dynamic_configs.forms.money.MoneyField",
            "label": "Money",
            "help_text": "An amount with at most 2 decimal places, e.g. 9.99",
        },
        "money_currency": {
            "type": "dynamic_configs.types.money.Money",
            "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
            "form": "dynamic_configs.forms.money.MoneyCurrencyField",
            "label": "Money with currency",
            "help_text": "An amount with at most 2 decimal places, and a 3-letter currency code",
            "raw_help_text": "An amount with at most 2 decimal places and a 3-letter currency code, e.g. 9.99 CAD",
            "sort_key": "dynamic_configs.types.money.by_currency_then_amount",
        },
    },
}
```

Both are listable and hashable, so `list:money`, `set:money`, `list:money_currency` and `set:money_currency` exist
when they're enabled.

## Writing a type: `money`

`money` is an amount: its Python type is `Decimal`, so it needs no class of its own, only a serializer.

The rule every amount follows lives in one function. **More than 2 decimal places is rejected, never rounded.** The
test is by digits, not value: more than 2 digits after the decimal point is rejected even when the extra digits are
zeros, so `9.990` and `9.999` are both rejected. For a `Decimal` from code this means an exponent below -2
(`Decimal("9.990").as_tuple().exponent == -3`). Amounts are always stored and shown with exactly 2 places: `10` is
stored as `"10.00"`. Negative amounts are allowed.

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: check_amount
```

The serializer applies the rule in both directions. `deserialize` accepts only plain decimal text
(`^-?\d+(\.\d+)?$` after stripping whitespace), so `1e3`, `1,000`, `+5`, `NaN` and `Infinity` are rejected, and
`serialize` applies the same rule to values from code, so `update("PRICE", Decimal("9.999"))` raises
`ConfigValueError`:

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: MoneySerializer
```

The serializer alone would make a working type: without a `form`, the admin shows a text input cleaned by
`deserialize`. `money` names a form field to get a number input with the same limit:

```{literalinclude} ../src/dynamic_configs/forms/money.py
:language: python
:pyobject: MoneyField
```

Since the serializer is the check every path runs (code, the admin's form, a list's raw mode), the form field only
shapes how the amount is entered.

## Extending a type: `money_currency`

`money_currency` adds a currency code to the amount, reusing everything `money` does.

Its Python type, `Money`, is a frozen dataclass, so it's immutable and hashable (which gives it a set variant). Its
`__post_init__` validates both parts (the amount by the `money` rule, the currency as exactly 3 uppercase letters)
and raises `ValueError`, so an invalid `Money` can't be created. `str(Money(...))` is `"9.99 CAD"`.

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: Money
```

`MoneyCurrencySerializer` **subclasses `MoneySerializer`** and reuses its amount parsing and formatting, adding the
currency code. Stored text is `"9.99 CAD"`; on input the code is uppercased, so `"9.99 cad"` is accepted:

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: MoneyCurrencySerializer
```

Currency codes are checked for shape (3 letters), not against the ISO 4217 list, so there's no data file to keep
current.

Its form field is a `MultiValueField`: `MoneyField` for the amount and a 3-character input for the currency, side by
side, with no JavaScript. Because that input isn't typed as one line, the `TYPES` entry gives a `raw_help_text`
saying how to type an item on a line of a list's raw mode (`9.99 CAD`).

```{literalinclude} ../src/dynamic_configs/forms/money.py
:language: python
:pyobject: MoneyCurrencyField
```

## Sorting: `by_currency_then_amount`

`Money` defines no order, since amounts in different currencies don't compare, so the list editor couldn't sort a
`list:money_currency` by value. Its entry names a `sort_key` instead, which sorts by currency, then amount
(`10.00 CAD, 5.00 USD, 20.00 USD`):

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: by_currency_then_amount
```

`money` needs no key: a `Decimal` already sorts by value.

## Using them

```python
from decimal import Decimal

import dynamic_configs
from dynamic_configs.types.money import Money

dynamic_configs.get_or_create("SHIPPING_FEE", "money", Decimal("4.5"))  # stored as "4.50"
dynamic_configs.get_or_create("GIFT_CARD_VALUES", "set:money_currency", [Money(Decimal("25"), "CAD")])
dynamic_configs.get("SHIPPING_FEE")  # Decimal("4.50")
```

An `int` is accepted for `money` too, and becomes a `Decimal` (see [The type check](types.md#the-type-check)).
