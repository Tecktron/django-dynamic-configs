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

The rule every amount follows lives in one function. **More than 2 decimal places is rejected, never rounded** (unless
the type sets a [rounding](#rounding)). The test is by digits, not value: more than 2 digits after the decimal point is
rejected even when the extra digits are zeros, so `9.990` and `9.999` are both rejected. For a `Decimal` from code this
means an exponent below -2 (`Decimal("9.990").as_tuple().exponent == -3`). Amounts are always stored and shown with
exactly 2 places: `10` is stored as `"10.00"`. Negative amounts are allowed, but zero has no sign: `-0`, or a negative
amount that rounds to zero, is stored as `"0.00"`.

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: check_amount
```

The rule doesn't depend on the thread's `decimal` context: `check_amount` works in a fixed one (28 digits, errors
raised), so a small amount isn't refused, and an amount too large is an error rather than `NaN`. The serializer applies
the rule in both directions. `deserialize` accepts only plain decimal text
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

### Rounding

To round instead of refusing, give the type a `rounding` through the entry's `options`. It is one of decimal's eight
constants: `ROUND_UP`, `ROUND_DOWN`, `ROUND_CEILING`, `ROUND_FLOOR`, `ROUND_HALF_UP`, `ROUND_HALF_DOWN`,
`ROUND_HALF_EVEN` and `ROUND_05UP`. They are plain strings, so `decimal.ROUND_HALF_UP` and `"ROUND_HALF_UP"` both work.
Anything else is a `dynamic_configs.E003` error.

```python
import decimal

DYNAMIC_CONFIGS = {
    "TYPES": {
        "money": {
            "type": "decimal.Decimal",
            "serializer": "dynamic_configs.types.money.MoneySerializer",
            "options": {"rounding": decimal.ROUND_HALF_UP},
            "form": "dynamic_configs.forms.money.MoneyField",
        },
    },
}
```

With that, `9.946` is stored as `"9.95"`, whether it comes from the admin, a list's raw mode or code
(`update("PRICE", Decimal("9.946"))`). The package's money fields (and subclasses of them) then accept more than 2
places in the admin and the serializer rounds. Another `form` keeps its own validation, so a 2-place field there still
refuses `9.946`; the serializer still rounds whatever text reaches it. Without `rounding` (or with `None`), 3 places are
refused as before. The rounding is set per type, so you can register two types with different rules.

`money_currency` takes the same option and rounds the text it reads. `Money(...)` in code still refuses 3 places, so
give it an amount that is already rounded.

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
currency code. Stored text is `"9.99 CAD"`; on input the code is uppercased, so `"9.99 cad"` is accepted. Only the
letters A to Z count, so a look-alike such as a dotless "ı" is refused:

```{literalinclude} ../src/dynamic_configs/types/money.py
:language: python
:pyobject: MoneyCurrencySerializer
```

Entered currency codes are checked for shape (3 letters), not against a list: `XYZ` is accepted. The package keeps a
list of ISO 4217 codes only to suggest them in the admin (see [Currency suggestions](#currency-suggestions)), so a list
that is out of date never refuses a value.

Its form field is a `MultiValueField`: `MoneyField`'s own number input for the amount, and a 3-character input for the
currency that suggests codes as you type, side by side. The inputs need no JavaScript; the admin's dropdown (see
[Currency suggestions](#currency-suggestions)) is a script on top. Because that input isn't typed as one line,
the `TYPES` entry gives a `raw_help_text` saying how to type an item on a line of a list's raw mode (`9.99 CAD`).

```{literalinclude} ../src/dynamic_configs/forms/money.py
:language: python
:pyobject: MoneyCurrencyField
```

### Currency suggestions

The currency input has a `<datalist>`, so the browser offers codes while you type. By default these are the ISO 4217
currencies, as published by SIX Group, the ISO 4217 maintenance agency (the date of the list the package carries is
`dynamic_configs.types.iso4217.PUBLISHED`). Funds, precious metals, bond market units and the codes for testing (`XTS`)
and for no currency (`XXX`) are left out. Each suggestion's text is the code and ISO's name for it as published, such
as `GBP - Pound Sterling` or `USD - US Dollar`; a suggestion with no label is the code alone.

In the admin, the input opens its own dropdown, in the admin's colours, with one click. It filters as you type, listing
the codes that start with what you typed first and then the suggestions whose text has it, and you choose with the arrow
keys and Enter, or the mouse; Escape, or a press anywhere else, closes it. Outside the admin, and in the admin if its
script doesn't run, the browser shows its own list, which looks and opens differently from one browser to the next
(Firefox opens it on a second click).

Give the type a `currencies` option to suggest your own. A list of codes suggests just those, with ISO's names for the
ones it knows; a mapping of code to label uses your labels as given; an empty list turns the suggestions off. Codes are
3 capital letters A to Z and labels are plain strings (a lazily translated label is refused). Anything else, such as a
bare string, is a `dynamic_configs.E003` error. It can be combined with `rounding`:

```python
import decimal

DYNAMIC_CONFIGS = {
    "TYPES": {
        "money_currency": {
            "type": "dynamic_configs.types.money.Money",
            "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
            "options": {"currencies": ["CAD", "USD"], "rounding": decimal.ROUND_HALF_UP},
            "form": "dynamic_configs.forms.money.MoneyCurrencyField",
        },
    },
}
```

With a mapping, `{"currencies": {"CAD": "Canadian dollar", "USD": "US dollar"}}`, the labels are yours.

Suggestions never restrict: the input still takes any 3 letters, so a code that isn't suggested (`XYZ`, or a currency
too new for the list) is accepted. The package refreshes its list every month (the maintainer's side of it is under
[The currency list](development.md#the-currency-list)), and a list that is a few weeks behind only means a new code
isn't suggested yet. If you write your own serializer with a `currencies` attribute, it must be a mapping of code to
label, since the form field draws its `.items()`.

### Decimal places

Every amount has 2 decimal places, although ISO 4217 gives some currencies 0 (JPY, KRW) and some 3 (KWD, BHD). That is a
known limit, and on purpose: 2 places is a one-size-fits-most choice for an example whose job is to show how to extend
the package by writing and registering your own types. A project that needs each currency's minor units writes its own
type; ISO's list gives them as `CcyMnrUnts`.

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
