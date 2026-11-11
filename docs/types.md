# Types

Every setting has a type, chosen when it's created and fixed after that. The type decides three things: the Python
type code reads, the text stored in the database, and the input the admin shows. Types come only from code (the
built-ins and the custom types in your settings); nothing an admin enters is ever imported, evaluated or executed.

## Built-in types

| Key        | Label          | Python type        | Stored text                                  | Admin input                           |
|------------|----------------|--------------------|----------------------------------------------|---------------------------------------|
| `str`      | String         | `str`              | as is; single line                           | `CharField`                           |
| `text`     | Text           | `str`              | as is; may contain newlines                  | `CharField` + `Textarea`              |
| `int`      | Integer        | `int`              | `str(value)`; parsing is strict (`"1.0"` is invalid) | `IntegerField`               |
| `float`    | Float          | `float`            | `repr(value)`; NaN and infinity rejected     | `FloatField`                          |
| `decimal`  | Decimal        | `Decimal`          | `str(value)`; NaN and infinity rejected      | `DecimalField`                        |
| `bool`     | Boolean        | `bool`             | `"true"` / `"false"`; parses true/false, 1/0, yes/no, on/off (any case) | `BooleanField`, or `NullBooleanField` when `allow_null` |
| `date`     | Date           | `date`             | ISO 8601 (`2026-11-01`)                      | `DateField` + admin date widget       |
| `datetime` | Date and time  | `datetime`         | ISO 8601 (see [Datetimes and time zones](#datetimes-and-time-zones)) | `ZonedDateTimeField` + admin pickers |
| `json`     | JSON           | `dict` or `list`   | `json.dumps(value, ensure_ascii=False)`      | `JSONTextField`, with the JSON editor |
| `seconds`  | Seconds        | `timedelta`        | the number of seconds (`"90"`, `"1.5"`)      | `DurationUnitField("seconds")`        |
| `minutes`  | Minutes        | `timedelta`        | the number of minutes                        | `DurationUnitField("minutes")`        |
| `hours`    | Hours          | `timedelta`        | the number of hours                          | `DurationUnitField("hours")`          |
| `days`     | Days           | `timedelta`        | the number of days                           | `DurationUnitField("days")`           |
| `weeks`    | Weeks          | `timedelta`        | the number of weeks                          | `DurationUnitField("weeks")`          |

Durations are one type per unit, which is clearer for admins than a free-form duration syntax: the admin enters `1.5`
for an `hours` setting and code reads `timedelta(hours=1.5)`. Numbers are written without a trailing `.0` (`"2"`, not
`"2.0"`).

A `str` must be a single line; use `text` for several lines. A `json` value must be an object or an array: a lone
number or string is rejected ("Enter a JSON object or array."), and so are NaN and infinity. The admin shows a
`json` value pretty-printed (`indent=2`) in the [JSON editor](admin.md#the-json-editor).

A `json` value may nest at most 128 levels deep (`dynamic_configs.types.serializers.JSON_MAX_DEPTH`). Each object or
array is one level, so `[[1]]` is 2 levels deep, and brackets inside strings don't count. A deeper value is refused
when it's saved ("The value can't be stored as JSON: it's nested too deeply (the limit is 128 levels)."), and the admin
says the same about deeper text ("The JSON is nested too deeply: the limit is 128 levels."). A deeper stored value,
which only a hand-edited row can hold, can't be read, like any other unreadable value (see
[Failure handling](failures.md)).

The limit is fixed because Python's own JSON reader and writer fail at a depth that depends on the stack of the thread
running them: tens of thousands of levels in a main thread, a few hundred in a thread with a small stack. Without the
limit, the same value could save in one process and fail to read in another.

## The type check

Every value passed to `get_or_create` or `update`, and every value produced by an admin form, is checked with
`isinstance` against the type's Python type, with these exceptions:

- `bool` is rejected where the Python type is `int`, `float` or `Decimal` (in Python, `bool` is a subclass of `int`).
- `datetime` is rejected for `date` (in Python, `datetime` is a subclass of `date`).
- An `int` is accepted where the Python type is `float` or `Decimal`, and converted. These rules go by Python type,
  so they apply to custom types too (an `int` given to the `money` type becomes a `Decimal`).
- A naive `datetime` is accepted and interpreted in Django's `TIME_ZONE` (see
  [Datetimes and time zones](#datetimes-and-time-zones)).
- For list types: the value must be a `list` or `tuple` (returned as a `list`), and each item is checked against the
  item type.
- For set types: the value must be a `set`, `frozenset`, `list` or `tuple` (returned as a `frozenset`), and each item
  is checked against the item type. A `list` or `tuple` containing duplicates raises `ConfigValueError`.

A failed check raises `ConfigTypeError`. A value of the right type that the type doesn't allow (a NaN float, a `str`
containing a newline) raises `ConfigValueError`.

## Datetimes and time zones

The `datetime` type follows Django's time zone settings.

- **`USE_TZ = True`** (Django's default): a naive datetime, from code or from text, is interpreted in Django's
  `TIME_ZONE`. So `17:00` with no zone, under `TIME_ZONE = "America/New_York"`, means 17:00 New York time. An aware
  datetime keeps its zone. The value is stored in UTC (`2026-11-02T22:00:00+00:00`), so the instant is kept, and read
  back as an aware datetime in UTC, as Django's ORM returns them. A local time that's ambiguous or doesn't exist
  around a daylight-saving change, given from code, is resolved by Python's `zoneinfo` rules (`fold=0`).
- **`USE_TZ = False`**: an aware datetime is converted to `TIME_ZONE` and made naive, which is Django's own convention
  for this mode; values are stored and returned naive.

As text (a list's raw mode, say), a datetime is written `YYYY-MM-DD HH:MM`, optionally with seconds and a UTC offset
(`2026-11-02 17:00+09:00`); one without an offset is in `TIME_ZONE`.

In the admin, with `USE_TZ` on, a datetime is entered as a date, a time and a time zone. The zones are labelled with
their current UTC offset, such as `America/New_York (-5:00)`, and the select starts on the current time zone. A time
that a daylight-saving change skips or repeats is a form error there, rather than guessed. With `USE_TZ` off, the
admin shows Django's split date and time pickers, and times are in the server's time zone. See
[Admin and skins](admin.md#datetimes) for the details.

## List and set types

Every type that's listable gets a list variant, keyed `list:<key>` and labelled `List of <label>`. If its Python type
is also hashable, it gets a set variant too, keyed `set:<key>` and labelled `Set of <label>`. Every built-in except
`json` (already a structure) is listable and hashable, so each has both: `list:int`, `set:str`, `list:datetime`,
`set:hours`, and so on.

- **Python type:** a `list` of the item type, or a `frozenset` for set types (read-only, and usable as a dict key or
  in comparisons).
- **Stored text:** a JSON array of each item's stored text, such as `["1", "2"]` for `list:int`. Set types keep the
  order the items were first entered, so the admin page doesn't reshuffle them. Custom types get the same treatment
  through their own serializer.
- **Duplicates:** a set type rejects duplicates rather than dropping them, compared after parsing, so `1` and `01`
  are the same item in a `set:int`.
- **Admin input:** the [list editor](admin.md#the-list-editor).

```python
dynamic_configs.get_or_create("FEATURED_TAGS", "list:str", ["news", "events"])
dynamic_configs.get_or_create("BLOCKED_IDS", "set:int", {3, 7})
dynamic_configs.get("BLOCKED_IDS")  # frozenset({3, 7})
```

The list editor's Sort button sorts by the item type's `sort_key` (see [Custom types](#custom-types)), or by the
values themselves when the type defines an order. `str` and `text` sort ignoring case (`apple, Zebra`, not
`Zebra, apple`); other built-ins sort by value (booleans false first).

## Custom types

A custom type is a Python class and a serializer, declared in `DYNAMIC_CONFIGS["TYPES"]`. Every value is a dotted path
except `label`, `help_text`, `raw_help_text` and `listable`:

```python
DYNAMIC_CONFIGS = {
    "TYPES": {
        "color": {
            "type": "myapp.colors.Color",                 # required
            "serializer": "myapp.colors.ColorSerializer",  # required
            "form": "myapp.forms.ColorField",              # optional: a django.forms.Field subclass
            "label": "Color",                              # optional, defaults to the key
            "help_text": "Pick a color",                   # optional, defaults to "": help for the form's input
            "raw_help_text": "A hex color, e.g. #1a2b3c",  # optional, defaults to help_text: a list's raw mode
            "listable": True,                              # optional, defaults to True: list and set variants
            "sort_key": "myapp.colors.hue",                # optional: item -> what list items sort by
            # or "sort_compare": "myapp.colors.compare",   # optional: (a, b) -> negative, zero or positive
        },
    },
}
```

- Keys must match `^[A-Za-z][A-Za-z0-9_]*$` (no `:`, which is reserved for list and set variants).
- A key that matches a built-in replaces that built-in.
- A listable custom type gets a set variant only if its class is hashable (`__hash__` isn't `None`).
- Mistakes are reported by the system checks at startup (see [System checks](installation.md#system-checks)).

[Worked example: the money types](money.md) builds two custom types step by step.

### The serializer

A serializer is a class with two methods. It's created once, with no arguments, when the types are loaded.

```python
class ColorSerializer:
    def serialize(self, value: Color) -> str: ...  # raises ValueError when the value is invalid
    def deserialize(self, text: str) -> Color: ...  # raises ValueError when the text is invalid
```

Raising `ValueError` is how a serializer rejects a value, in both directions:

- From `deserialize`: the admin shows it as a form error, and a stored value that fails it is unreadable (see
  [Failure handling and logging](failures.md)).
- From `serialize`: `get_or_create` and `update` raise `ConfigValueError` (the value has the right type but isn't
  allowed).

Error messages are shown to admins as form errors. Don't put the value itself in them: settings may hold secrets.

### The form field

Without a `form`, the admin uses `SerializerField`: a text input that calls `deserialize` to clean what's typed and
`serialize` to show the value. Its spaces follow [`STRIP_STRINGS`](installation.md#strip_strings).

A `form` is a `django.forms.Field` subclass, for a richer input (a colour picker, a widget of several parts). It's
created with `required=False`, `label` and `help_text`. The admin form applies the empty-value rules itself (see
[Admin and skins](admin.md#empty-values)), so they hold even when `allow_null` changes in the same save, and the
cleaned value must pass the type check.

The serializer is the one check every path runs. A list item's `form` runs only when the item is added or updated in
the list editor; raw mode, the field without JavaScript, saving and code check items with the serializer alone. So a
rule a value must always follow belongs in `deserialize`, and `form` shapes how the value is entered.

### Help text

`help_text` describes the type's own input. The admin shows it under the value on the add and change pages, and under
the list editor's item editor.

A list's raw mode (one item per line) says what to type on each line: "One item per line. Each item: …" with the
type's `raw_help_text`, or its `help_text` when it has none. For an input that's a text box, typing in it and typing a
line are the same, so set `raw_help_text` only when the input isn't typed as one line (a widget of several parts,
say), to say how an item is typed on a raw-mode line.

### Sorting

`sort_key` or `sort_compare`, not both, sets how the list editor sorts a list of the type:

- `sort_key`: the dotted path of a function from an item to what to sort by, as for `sorted(key=...)`.
- `sort_compare`: the dotted path of a function comparing two items, returning a negative number, zero or a positive
  number. It's turned into a key with `functools.cmp_to_key`.

With neither, a list sorts by the values themselves if the class defines an order (its own `__lt__`, or a dataclass
with `order=True`); otherwise the list editor has no Sort button. A key that fails on some value doesn't break the
page: the editor says "These items can't be sorted." and leaves the list alone.

### Constraints as custom types

There are no per-setting validators. A constraint such as "a positive number of hours" is a custom type whose
serializer rejects bad values. Subclassing a built-in serializer keeps its parsing and formatting:

```python
# myapp/config_types.py
from datetime import timedelta

from dynamic_configs.types.serializers import HoursSerializer


class PositiveHoursSerializer(HoursSerializer):
    """A number of hours greater than zero."""

    def serialize(self, value: timedelta) -> str:
        self.check(value)
        return super().serialize(value)

    def deserialize(self, text: str) -> timedelta:
        return self.check(super().deserialize(text))

    def check(self, value: timedelta) -> timedelta:
        if value <= timedelta(0):
            raise ValueError("Enter a number of hours greater than zero.")
        return value
```

```python
DYNAMIC_CONFIGS = {
    "TYPES": {
        "positive_hours": {
            "type": "datetime.timedelta",
            "serializer": "myapp.config_types.PositiveHoursSerializer",
            "label": "Hours (positive)",
            "help_text": "A number of hours greater than zero, e.g. 1.5.",
        },
    },
}
```

`get_or_create("TOKEN_LIFETIME", "positive_hours", timedelta(hours=0))` then raises `ConfigValueError`, and the admin
shows "Enter a number of hours greater than zero." under the value. The type also gets `list:positive_hours` and
`set:positive_hours`.
