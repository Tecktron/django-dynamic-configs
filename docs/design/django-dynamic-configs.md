# django-dynamic-configs: design

Status: draft for review, 2026-11-02.

## Purpose

A reusable, public Django app for runtime configuration: typed values that can be **added** and edited in the Django
admin, and read from code through a small, cached API. It replaces hand-rolled per-project settings models.

### Goals

- Admins can add, edit and delete settings; each has a unique name, a type, a value and an optional description.
- A clean programmatic API: `get`, `get_or_create`, `update`, `delete`, plus async variants.
- Typed values, including list and set variants of every type except JSON, and custom types declared in Django
  settings.
- Nothing an admin enters is ever imported, evaluated or executed. Types come only from code.
- Cached reads when a cache is configured; a caller that passes a default is never broken by an outage.
- Works under admin skins (jazzmin, grappelli, unfold) by using stock admin pages.
- Optional, explicit integration with django-simple-history. It isn't required.
- Test helpers that need neither the database nor the cache.
- Supports Django 5.2+ and every Python each supported Django release supports. 100% branch coverage of our code.
- Clear logging at the proper levels, docstrings and comments throughout, and a documentation site on Read the Docs.

### Non-goals (v1)

- Per-setting validators. Constraints are expressed as custom types (see Types).
- Settings declared in Django settings and seeded on migrate. `get_or_create` covers this.
- Inline editing on the admin list page.

## Data model

One model, `dynamic_configs.models.Config`, table `dynamic_configs_config`:

| Field         | Definition                          | Notes                                                    |
|---------------|-------------------------------------|----------------------------------------------------------|
| `name`        | `CharField(255, primary_key=True)`  | must match `^[A-Z][A-Z0-9_]*$`; read-only after creation |
| `type`        | `CharField(64)`                     | registry key (`"hours"`, `"list:int"`, `"set:str"`); read-only after creation |
| `value`       | `TextField(null=True)`              | the serialized value; `NULL` means empty                 |
| `allow_null`  | `BooleanField(default=False)`       | whether the value may be empty (`None`)                  |
| `description` | `TextField(blank=True, default="")` | optional, for admins                                     |
| `created_on`  | `DateTimeField(auto_now_add=True)`  |                                                          |
| `modified_on` | `DateTimeField(auto_now=True)`      |                                                          |

Ordering is by `name`. `type` deliberately has no `choices=`: choices are written into migrations, so every project
adding a custom type would get a spurious migration. The admin form and the API validate `type` against the registry.

## Types

### Serializer protocol

A serializer is a class with two methods. It is instantiated once, with no arguments, when the registry is built.

```python
class ColorSerializer:
    def serialize(self, value: Color) -> str: ...  # raises ValueError when the value is invalid
    def deserialize(self, text: str) -> Color: ...  # raises ValueError when the text is invalid
```

Raising `ValueError` is the validation mechanism, in both directions:

- From `deserialize`: the admin shows it as a form error, and a stored value that fails it is "unreadable" (see
  Failure handling).
- From `serialize`: `get_or_create` and `update` raise `ConfigValueError` (the value has the right type but isn't
  allowed, such as a NaN float or a `str` containing a newline).

Constraints such as "a positive number of hours" are expressed as a custom type whose serializer rejects bad values.

### Type check

Every value passed to `get_or_create` or `update`, and every value produced by a form, is checked with `isinstance`
against the type's Python type, with these exceptions:

- `bool` is rejected where the Python type is `int`, `float` or `Decimal` (in Python, `bool` is a subclass of `int`).
- `datetime` is rejected for `date` (in Python, `datetime` is a subclass of `date`).
- An `int` is accepted where the Python type is `float` or `Decimal`, and converted. These rules go by Python type,
  so they apply to custom types too (an `int` given to the `money` type becomes a `Decimal`).
- A naive `datetime` is accepted and interpreted in Django's `TIME_ZONE` (see Datetimes and time zones).
- For list types: the value must be a `list` or `tuple` (returned as a `list`), and each item is checked against the
  item type.
- For set types: the value must be a `set`, `frozenset`, `list` or `tuple` (returned as a `frozenset`), and each item
  is checked against the item type. A `list` or `tuple` containing duplicates raises `ConfigValueError`.

A failed check raises `ConfigTypeError`.

### Built-in types

| Key        | Label          | Python type        | Stored text                                  | Form field                            |
|------------|----------------|--------------------|----------------------------------------------|---------------------------------------|
| `str`      | String         | `str`              | as is; single line                           | `CharField`                           |
| `text`     | Text           | `str`              | as is; may contain newlines                  | `CharField` + `Textarea`              |
| `int`      | Integer        | `int`              | `str(value)`; parsing is strict (`"1.0"` is invalid) | `IntegerField`               |
| `float`    | Float          | `float`            | `repr(value)`; NaN and infinity rejected     | `FloatField`                          |
| `decimal`  | Decimal        | `Decimal`          | `str(value)`; NaN and infinity rejected      | `DecimalField`                        |
| `bool`     | Boolean        | `bool`             | `"true"` / `"false"`; parses true/false, 1/0, yes/no, on/off (any case) | `BooleanField`, or `NullBooleanField` when `allow_null` |
| `date`     | Date           | `date`             | ISO 8601 (`2026-11-01`)                      | `DateField` + admin date widget       |
| `datetime` | Date and time  | `datetime`         | ISO 8601 (see Datetimes and time zones)      | `ZonedDateTimeField` + admin pickers  |
| `json`     | JSON           | `dict` or `list`   | `json.dumps(value, ensure_ascii=False)`      | `JSONTextField` (see below)           |
| `seconds`  | Seconds        | `timedelta`        | the number of seconds (`"90"`, `"1.5"`)      | `DurationUnitField("seconds")`        |
| `minutes`  | Minutes        | `timedelta`        | the number of minutes                        | `DurationUnitField("minutes")`        |
| `hours`    | Hours          | `timedelta`        | the number of hours                          | `DurationUnitField("hours")`          |
| `days`     | Days           | `timedelta`        | the number of days                           | `DurationUnitField("days")`           |
| `weeks`    | Weeks          | `timedelta`        | the number of weeks                          | `DurationUnitField("weeks")`          |

Durations are per-unit types, which are clearer for admins than a free-form duration syntax: the admin enters `1.5`
for an `hours` setting and code reads `timedelta(hours=1.5)`. Numbers are written without a trailing `.0` (`"2"`, not
`"2.0"`).

A `json` value nests at most 128 levels deep (`JSON_MAX_DEPTH` in `types/serializers.py`; each object or array is a
level, so `[[1]]` is 2). Saving refuses a deeper value ("The value can't be stored as JSON: it's nested too deeply (the
limit is 128 levels)."), and reading refuses deeper text ("The JSON is nested too deeply: the limit is 128 levels."),
so a hand-edited row that deep is unreadable like any other. Both are checked before Python's `json` runs: reading
counts brackets outside strings, and writing walks the value with a to-do list rather than recursion. A value that
contains itself still gets its own message. Python's `json` recurses once per level and fails where the thread's stack
runs out, so without a fixed limit the depth that works depends on where the code runs. Measured on Python 3.14.4: 605
levels in a thread with a 128 KB stack, 3,336 with 512 KB, 6,977 with 1 MB, 57,949 in an 8 MB main thread, and no
limit with an unlimited stack. 128 is the limit Rust's serde_json uses (.NET uses 64, Ruby 100), and RFC 8259 §9
allows parsers to set one. Lists use their own parsing, which already treats anything but a flat array of strings as
unreadable.

Every type, built-in or custom, has a short `help_text` (for example "YYYY-MM-DD" for `date`, "one number of hours,
e.g. 1.5" for `hours`). The admin shows help that describes the input on screen:

- `help_text` is the help for the type's own input: the value's help on the add and change pages, and the list
  editor's item editor's.
- A list's raw textarea says what to type on each line: "One item per line. Each item: …" with the type's
  `raw_help_text`, or its `help_text` when it has none. For an input that's a text box, typing in it and typing a line
  are the same, so only a type whose input isn't typed as one line (a custom type's widget of several parts, say)
  needs `raw_help_text`.
- The built-in `bool` and `datetime` replace their help beside their widgets: the checkbox ("Checked means true."),
  the yes/no/unknown select ("Unknown leaves the setting empty, which needs Allow null checked.") and the datetime
  picker (see below). Their `help_text` describes typed text, which raw mode shows.
- Under a list or set field goes only what holds both ways: "No repeats." for a set.

`JSONTextField` is a textarea (`JSONTextarea`, marked for the admin's JSON editor, with spell-checking off) showing
the value pretty-printed (`indent=2`), validated on the server. In the admin it gets the JSON editor (see Admin).

### Datetimes and time zones

The `datetime` type follows Django's time zone settings:

- **`USE_TZ = True`** (Django's default): a naive datetime, from code or from text, is interpreted in Django's
  `TIME_ZONE` (`django.utils.timezone.make_aware` with the default time zone). So `17:00` with no zone, under
  `TIME_ZONE = "America/New_York"`, means 17:00 New York time. An aware datetime keeps its zone. The value is stored
  normalised to UTC (`2026-11-02T22:00:00+00:00`), so the instant is preserved, and read back as an aware datetime in
  UTC, as Django's ORM returns them. Local times that are ambiguous or don't exist around a daylight-saving change are
  resolved by Python's `zoneinfo` rules (`fold=0`).
- **`USE_TZ = False`**: an aware datetime is converted to `TIME_ZONE` and made naive, which is Django's own convention
  for this mode; values are stored and returned naive.
- **In the admin** (with `USE_TZ` on), a datetime is entered as a date, a time and a time zone: the admin's date and
  time pickers plus a select of IANA zones (`ZonedDateTimeField`). Each zone is labelled with its current UTC offset,
  such as `America/New_York (-5:00)`, and the zones run from the most negative offset to the most positive, by name
  within an offset, with UTC first among those at `+0:00`; `localtime` and `Factory` aren't offered, since they
  aren't real zones. The labels follow daylight saving, refreshed hourly. The select starts on the current time
  zone (`TIME_ZONE` unless the project activates another), and a stored value is shown in that zone. UTC stands in
  when the select doesn't offer the current zone (a fixed offset a project activates) or a value can't be moved into
  it (near year 1 or 9999), so the page opens and saving it untouched keeps the instant. When the value
  is empty, the admin script starts the select on the browser's own zone instead, and it keeps each widget's Today
  and Now links and time zone note in that widget's chosen zone. The script also puts "My zone | Server zone" links
  beside the select, picking the browser's zone or `TIME_ZONE`; a link is left out when the select doesn't offer
  its zone. A time that a daylight-saving change skips or repeats is a form error
  rather than resolved with `fold=0`: the admin typed it, so it isn't guessed. The value's help reads "A date, a
  time and the time zone they're in." rather than the typed format, which still applies to code, list items and text.
- **In the admin with `USE_TZ` off** there are no zones to choose: the value uses Django's split date and time
  pickers, and its help reads "A date and a time. Times are in the server's time zone (<TIME_ZONE>)." The zone note
  appears only in this mode.
- In the admin's list editor, an item of a `list:datetime` or `set:datetime` is entered in the datetime's own fields
  (date, time and zone; see Admin). In raw mode, and in the admin without JavaScript, items are typed as text, one per
  line; an item can carry its zone as a UTC offset (`2026-11-02 17:00+09:00`), and one without is in `TIME_ZONE`.

### List and set types

Every type whose registry entry has `listable=True` gets a list variant, keyed `list:<key>` and labelled
`List of <label>`. If its Python type is also hashable, it gets a set variant too, keyed `set:<key>` and labelled
`Set of <label>`. Built-ins are listable except `json` (already a structure); every listable built-in is hashable, so
each gets both variants. (`text` was left out while the admin edited lists one item per line, which can't hold an item
with a line break; the list editor can, so `list:text` and `set:text` exist.)

- Python type: a `list` of the item type, or a `frozenset` for set types (read-only, and usable as a dict key or in
  comparisons).
- Stored text: a JSON array of each item's serialized string, e.g. `["1", "2"]` for `list:int`. Set types keep the
  order the items were first entered, so the admin page doesn't reshuffle them. Custom types get the same treatment
  through their own serializer.
- Form field: `TypedLineListField(item_type, unique=False)` (`dynamic_configs/forms/list.py`). It takes its value in
  either of two forms, and its widget says which:
  - **A list of stored texts**, from the admin's list editor (see Admin). Each is read with the item serializer's
    `deserialize` exactly as stored, so spaces, empty items and line breaks survive a save. An error names the item
    ("Item 3: …").
  - **Text, one item per line**: the list editor's raw mode, the admin without JavaScript, and the field's own
    textarea outside the admin. Every line is an item, blank ones included: an empty line is an empty item, or an
    error for item types that reject an empty input. An empty textarea is an empty list. An error names the line
    ("Line 3: …"). Lines of `str` items, and of custom types without a `form`, are stripped only as `STRIP_STRINGS`
    says (see Configuration); `text` lines are kept exactly; other item types' lines are stripped before parsing,
    since spaces around a number or a date are never part of it. Two values can't be shown exactly one item per line:
    one with an item containing a line break, and a list of one empty item (which reads back as an empty list). In
    this form the field shows either read-only, with a note that editing it needs JavaScript, and saving keeps the
    items exactly.

  Set types use `unique=True`: duplicates (compared after `deserialize`, so `1` and `01` match for `set:int`) are
  rejected with an error naming both ("Lines 2 and 5 are the same", or "Items 2 and 5 are the same"), not dropped
  silently. The textarea never gets `maxlength` or `minlength`: length limits apply to each item, which the browser
  can't check. It is a typed variant of `LineListField`, an untyped one-item-per-line field in the same module.
- Sorting, in the list editor: by the item type's `sort_key` (see Custom types), or by the values themselves when
  the type defines an order. `str` and `text` have a built-in key that ignores case (`apple, Zebra`, not
  `Zebra, apple`); other built-ins sort by value (booleans false first). Sorting by the displayed text instead would
  put `10` before `9`.

### Custom types

Declared in Django settings; every value is a dotted path except `label`, `help_text`, `raw_help_text` and
`listable`:

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
- A listable custom type gets a set variant only if its class is hashable (`__hash__` isn't `None`).
- A key that matches a built-in replaces that built-in.
- Without `form`, the admin uses `SerializerField(serializer)`: a text input that calls `deserialize` to clean and
  `serialize` to display.
- A `form` field is instantiated with `required=False`, `label` and `help_text`. The admin form applies the
  empty-value rules itself (see Admin), so they hold even when `allow_null` changes in the same save; the cleaned
  value must pass the type check.
- The serializer is the one check every path runs. A list item's `form` runs only when the item is added or updated
  in the list editor; raw mode, the field without JavaScript, saving and code check items with the serializer alone.
  So a rule a value must always follow belongs in `deserialize`, and `form` shapes how the value is entered.
- `sort_key` or `sort_compare`, not both, sets how the admin's list editor sorts a list of the type. A compare
  function is turned into a key with `functools.cmp_to_key` when the registry loads, so `ConfigType` holds one
  optional `sort_key`. With neither, a list sorts by the values themselves if the class defines an order (its own
  `__lt__`, or a dataclass with `order=True`); otherwise the list editor has no Sort button. A key that fails on some
  value doesn't break the page: the editor says "These items can't be sorted." and leaves the list alone.

### Included example types: money

Two working custom types ship with the package as the reference example of writing and extending a type. They are
**not registered by default**; a project enables either or both through `TYPES`, exactly as it would its own types:

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

**`money`: an amount** (`dynamic_configs/types/money.py`, `dynamic_configs/forms/money.py`)

- Python type `Decimal`.
- `MoneySerializer.deserialize` accepts only plain decimal text (`^-?\d+(\.\d+)?$` after stripping whitespace), so
  `1e3`, `1,000`, `+5`, `NaN` and `Infinity` are rejected. Negative amounts are allowed.
- **More than 2 decimal places is rejected, never rounded.** The test is by digits, not value: more than 2 digits
  after the decimal point is rejected even when the extra digits are zeros, so `9.990` and `9.999` are both rejected.
  For a `Decimal` from code this means an exponent below -2 (`Decimal("9.990").as_tuple().exponent == -3`).
- Amounts are always stored and displayed with exactly 2 places: `10` is stored as `"10.00"`.
- `MoneySerializer.serialize` applies the same rule to values from code (`Decimal("9.999")` raises
  `ConfigValueError`).
- `MoneyField` is a `DecimalField(decimal_places=2)`.

**`money_currency`: an amount and a currency, built on `money`**

- Python type `Money`: a frozen dataclass (`amount: Decimal`, `currency: str`), so it's immutable and hashable. Its
  `__post_init__` validates both parts (the amount by the `money` rule, the currency as exactly 3 uppercase letters)
  and raises `ValueError`, so an invalid `Money` can't be created. `str(Money(...))` is `"9.99 CAD"`.
- `MoneyCurrencySerializer` **subclasses `MoneySerializer`** and reuses its amount parsing and formatting, adding the
  currency code. Stored text is `"9.99 CAD"`; on input the code is uppercased (`"9.99 cad"` is accepted).
- `MoneyCurrencyField` is a `MultiValueField` combining `MoneyField` (the amount) with a 3-character currency input,
  shown side by side with no JavaScript.
- Currency codes are checked for shape (3 letters), not against the ISO 4217 list, so there is no data file to keep
  current.
- `Money` defines no order, since amounts in different currencies don't compare, so its entry gives the list editor a
  `sort_key`: `by_currency_then_amount` (in `types/money.py`) sorts by currency, then amount
  (`10.00 CAD, 5.00 USD, 20.00 USD`). It's the worked example of the key. `money` is a `Decimal`, which already sorts
  by value.

Both are listable and hashable, so `list:money`, `set:money`, `list:money_currency` and `set:money_currency` exist
when they're enabled. They're covered by the same 100% branch coverage rule as the rest of the package, plus a test
that enables them through `TYPES` and round-trips values through the API and the admin.

### Registry

`dynamic_configs.types.registry` builds the registry on first use: built-ins, then `TYPES` entries (importing their
dotted paths), then list and set variants. The registry is rebuilt when `DYNAMIC_CONFIGS` changes (the `setting_changed`
signal), so `override_settings` works in tests.

Django system checks validate the configuration at startup (`manage.py check`, and every `runserver`/`migrate`):

| Check                   | Condition                                                                |
|-------------------------|--------------------------------------------------------------------------|
| `dynamic_configs.E001`  | `DYNAMIC_CONFIGS` or `TYPES` has the wrong shape, an invalid key, an entry missing `type`/`serializer`, an entry with both `sort_key` and `sort_compare` or one that isn't callable, or `STRIP_STRINGS` isn't `True`, `False` or `None` |
| `dynamic_configs.E002`  | a dotted path can't be imported                                          |
| `dynamic_configs.E003`  | a serializer lacks a callable `serialize` or `deserialize`               |
| `dynamic_configs.E004`  | `form` is not a `django.forms.Field` subclass                            |
| `dynamic_configs.E005`  | `CACHE` names an alias that isn't in `CACHES`                            |
| `dynamic_configs.W001`  | (warning) an admin using `ConfigAdminMixin` sets `fields`, `fieldsets` or `readonly_fields`, which the mixin ignores (see Admin) |
| `dynamic_configs.E101`  | the simple-history sub-app is installed but `simple_history` isn't in `INSTALLED_APPS` |

## Public API

`dynamic_configs/__init__.py` must not import models, because it is imported while Django loads `INSTALLED_APPS`.
It exposes the API lazily (a module-level `__getattr__`). The functions live in `dynamic_configs/api.py`.

```python
from dynamic_configs import get, get_or_create, update, delete

get(name, default=<missing>, *, no_cache=False)  # -> value
get_or_create(name, type, value, *, description="", allow_null=False)  # -> (value, created)
update(name, new_value, *, allow_null=None)  # -> None
delete(name)  # -> bool
aget(...), aget_or_create(...), aupdate(...), adelete(...)  # async, same arguments
```

- **`get`** returns the deserialized value, or `None` for an empty `allow_null` setting. When the setting doesn't
  exist and no default was passed, it raises `ConfigDoesNotExist`. `no_cache=True` skips the cache read, then
  refreshes the cache entry with what it read.
- Names that don't match the name pattern can never be saved, so `get` treats them as missing without touching the
  cache or the database.
- **`get_or_create`** always reads the database, then refreshes the cache. When the setting exists, it returns the
  stored value and `created=False`; if the stored type differs from `type`, it raises `ConfigTypeError`. When it
  doesn't exist, it validates the name, the type key and the value, creates the setting, and returns
  `(value, True)`. Concurrent creation is handled by Django's `get_or_create`.
- **`update`** changes an existing setting inside a transaction (`select_for_update`). `allow_null=None` keeps the
  setting's flag; `True` or `False` updates it in the same save. `new_value=None` is accepted only when the
  resulting flag is `True`. It raises `ConfigDoesNotExist` if the setting is missing, `ConfigTypeError` if the value
  fails the type check, and `ConfigValueError` if the serializer rejects the value or the setting's type is no longer
  registered.
- **`delete`** returns `True` if it deleted the setting, `False` if it didn't exist. It never raises for a missing
  setting.
- **Async variants** wrap the sync functions with `asgiref.sync.sync_to_async`, so there is one implementation.
- **Overrides** from the test helpers (see Test helpers) take precedence in `get` and `get_or_create`.

### Exceptions

Defined in `dynamic_configs/exceptions.py`, except `ConfigDoesNotExist`, which needs the model and lives in
`models.py`. All are importable from `dynamic_configs`.

| Exception            | Bases                              | Raised when                                                 |
|----------------------|------------------------------------|-------------------------------------------------------------|
| `ConfigError`        | `Exception`                        | base class                                                  |
| `ConfigDoesNotExist` | `ConfigError`, `Config.DoesNotExist` | the setting doesn't exist (so `except ObjectDoesNotExist` works) |
| `ConfigTypeError`    | `ConfigError`, `TypeError`         | a value fails the type check; an unknown type key is passed; `get_or_create` finds a different type |
| `ConfigValueError`   | `ConfigError`, `ValueError`        | an invalid name; the serializer rejects a value; a set type is given duplicates; a stored value can't be deserialized; a stored type is no longer registered |

## Caching

- **Enabled** when `DYNAMIC_CONFIGS["CACHE"]` names a cache alias (default `"default"`) whose backend isn't
  `DummyCache`. `None` disables caching.
- **Per key:** `dynamic_configs:v1:<name>` holds the tuple `(type_key, stored_text)`, never a deserialized object,
  so custom classes are never pickled into the cache. `v1` lets a later release change the format safely.
  A name long enough to push the cache's full key past 250 characters (Memcached's limit) is keyed by its start and a
  hash of the whole name instead.
- **Missing settings** are cached as a marker, so `get(name, default)` for a nonexistent setting doesn't query the
  database on every call.
- **Timeout:** `DYNAMIC_CONFIGS["TIMEOUT"]`, default `300` seconds; `None` means no expiry (Django's semantics).
- **On save:** a `post_save` signal deletes the entry immediately (so reads inside the transaction go to the
  database), then replaces it with the new value when the transaction commits (`transaction.on_commit`), so a
  rolled-back save never reaches the cache.
- **On delete:** `post_delete` does the same, writing the missing marker on commit.
- If the cache is down while a setting is saved or deleted, the failure is logged as a warning and the save still
  succeeds; the old entry, if one is left, expires after `TIMEOUT`.
- Admin saves, `update`, `delete` and `get_or_create` all go through the model's `save`/`delete`, so they all trigger
  this. `QuerySet.update()`, `bulk_create()` and `bulk_update()` bypass signals; the README documents this.
  (`QuerySet.delete()` does send `post_delete` for each row, because a receiver is connected.)
- **Per-process caches:** with Django's default `LocMemCache`, an edit only refreshes the cache of the process that
  handled it; other processes see the old value until it expires. The README recommends a shared cache (Redis,
  Memcached) or a short `TIMEOUT`.

## Failure handling

One rule: **if you pass a default, `get` never raises.**

| Situation                                     | `get` with a default        | `get` without a default      |
|-----------------------------------------------|-----------------------------|------------------------------|
| Setting doesn't exist                         | returns the default         | raises `ConfigDoesNotExist`  |
| Cache error (read or write)                   | logged as a warning; falls through to the database | same                |
| Database error (`DatabaseError`)              | logged as a warning; returns the default | the error propagates  |
| Stored value unreadable, or its type isn't registered | logged as an error; returns the default | raises `ConfigValueError` |
| `allow_null` and empty                        | returns `None`              | returns `None`               |

A context-local re-entrancy guard (a `contextvars` flag set while the library is logging) suppresses logging from a
`get` that runs inside that logging, so a logging handler that itself calls `get` cannot recurse while the database
or cache is down.

## Logging

Each module logs to its own logger under `dynamic_configs` (`logging.getLogger(__name__)`: `dynamic_configs.api`,
`dynamic_configs.cache`, `dynamic_configs.types.registry`, ...), so projects can tune them together or separately.

| Level     | Used for                                                                                       |
|-----------|------------------------------------------------------------------------------------------------|
| `DEBUG`   | cache hits, misses and refreshes; database reads; the registry being built or rebuilt          |
| `INFO`    | writes made through the API: a setting created by `get_or_create`, changed by `update`, deleted by `delete` |
| `WARNING` | a cache error (falling through to the database); a database error answered with the default    |
| `ERROR`   | a stored value that can't be deserialized; a stored type that is no longer registered          |

- **Setting values are never logged, at any level**, because settings may hold secrets (API keys, tokens). Messages
  carry the setting's name and type key only.
- Messages use lazy `%`-style arguments, name the setting, and say what happens next (for example "Cache read failed
  for config %r; reading from the database"). Exceptions are logged with `exc_info`.
- Every record carries `extra={"config_name": ...}` (and `"config_type"` where known), so structured log handlers can
  filter on them.
- System check failures are reported through Django's checks framework, not logged.

## Code documentation

- Every public module, class, function and method has a docstring in reST field-list style (`:param:`, `:type:`,
  `:returns:`, `:rtype:`, `:raises:`), which Sphinx autodoc renders without extensions.
- Internal functions have docstrings too; comments explain *why* where the code alone doesn't (for example why
  `type` has no `choices=`, or why cache writes wait for `on_commit`).
- Type hints throughout; they also appear in the API reference.

## Configuration

```python
DYNAMIC_CONFIGS = {
    "CACHE": "default",       # cache alias, or None to disable caching
    "TIMEOUT": 300,           # cache timeout in seconds; None = no expiry
    "TYPES": {},              # custom types (see Types)
    "REGISTER_ADMIN": True,   # register ConfigAdmin automatically
    "STRIP_STRINGS": None,    # spaces at the ends of strings typed in the admin (see below)
}
```

All keys are optional. Settings are read through `dynamic_configs/conf.py`, which applies the defaults and is reset on
`setting_changed`.

`STRIP_STRINGS` decides whether the admin strips spaces from the ends of strings typed in a single-line input: `str`
values, the items of `list:str` and `set:str`, and custom types without a `form` (which get a plain text input). The
package makes no judgement about such spaces; the default is a sensible middle, and a project can choose either way:

| `STRIP_STRINGS`   | A single value | List and set items (item editor and raw mode)                  |
|-------------------|----------------|----------------------------------------------------------------|
| `None` (default)  | stripped       | kept exactly                                                   |
| `True`            | stripped       | stripped (so in a set, `" a"` and `"a"` are the same item)     |
| `False`           | kept exactly   | kept exactly                                                   |

It applies to the admin only: values set from code are always stored exactly. Config names are always stripped (a
name is an identifier, not a value), and `text` values and descriptions are always kept exactly.

## Admin

The admin ships **no templates** of its own; it uses stock `ModelAdmin` pages, so admin skins apply. Its scripts are
optional and every page works without them: `dynamic_configs/admin.js` fills in defaults and saves clicks,
`dynamic_configs/json_editor.js` is the JSON editor and `dynamic_configs/list_editor.js` the list editor, with
`dynamic_configs/admin.css`, which styles only the editors' own elements. Projects can still override the standard templates (`admin/dynamic_configs/config/change_form.html`).

- **`ConfigAdminMixin`** holds all the behaviour. **`ConfigAdmin`** is `ConfigAdminMixin` + `admin.ModelAdmin`, and is
  registered automatically by `dynamic_configs.admin.register_admin()` unless `REGISTER_ADMIN` is `False`; calling it
  again does nothing, so integrations can rely on it. Skins with their own base class (unfold) unregister it and
  register `ConfigAdminMixin` + their `ModelAdmin`.
- The mixin sets the fields, their layout and which are read-only itself (`get_fieldsets`, `get_readonly_fields`),
  since the add page's two steps and the locked name and type depend on them. So the `fields`, `fieldsets` and
  `readonly_fields` options are ignored, and `dynamic_configs.W001` warns when one is set; a subclass changes them by
  overriding those methods and calling `super()`.
- **List page:** name, type label, a value preview (list and set items joined with `, `, long values truncated),
  description and modified time. A list or set whose stored text isn't a JSON array of strings (a hand-edited row)
  previews as that text. Search on name and description; filter by type.
- **Add page:** two steps, so the value can use its type's own field. The first step asks only for the type (a
  select of registered types, including list and set variants); Save moves to the second step at
  `add/?type=<key>`, which shows the name, the type (read-only), the value in its type's form field, `allow_null` and
  the description, as on the change page. With the admin script, choosing a type moves on without clicking Save. An
  unknown `?type=` shows the first step again, and other query parameters (a popup's, say) are kept. A boolean gets
  the yes/no/unknown choice on this page, since whether the config allows None isn't known until it's saved.
- **Change page:** name and type are read-only; the value uses its type's form field (checkbox, date picker, the list
  editor, and so on).
- On both pages, an empty value is saved as `None` when `allow_null` is set. When it isn't set, an empty value is the
  empty string for `str` and `text`, an empty list or set for list and set types, and a "required" error for every
  other type. (So
  a `str` setting with `allow_null` can't hold the empty string through the admin; code can still `update` it to `""`.)
- **Whitespace:** on both pages the name is stripped, and `text` values and descriptions are kept exactly as typed.
  Strings typed in a single-line input (`str` values and items, and custom types without a `form`) follow
  `STRIP_STRINGS` (see Configuration): by default a single value is stripped and a list or set item is kept exactly.
- **Widgets:** Django's plain date, split date/time and textarea widgets are swapped for the admin's versions (date
  picker, styled textarea), and the zoned datetime widget gets the admin's date and time pickers, keeping their
  attributes. A type's own widget is never replaced, even one built on `Textarea`. List and set values get the list
  editor's widget (`AdminListEditorWidget`).
- **JSON editor:** the `json` type's textarea (`AdminJSONTextarea`) gets `json_editor.js` and `admin.css`:
  - A **Format** link re-indents the value, two spaces per level, and on invalid JSON, or JSON nested too deeply,
    changes nothing and moves the cursor to the problem.
  - **Enter** keeps the line's indent, adds a level after `{` or `[`, and between a pair of brackets puts the closing
    one on its own line. Tab is left alone, so it still moves to the next field.
  - A **closing bracket** typed on a line of nothing but indent steps back a level (two spaces or a tab), in the same
    undo step. It goes by the character typed (`beforeinput`), not the key, so AltGr layouts get it too. A bracket
    committed through an input method (IME), as some phone keyboards do, arrives as `insertCompositionText`, which
    can't be cancelled, so it doesn't adjust the indent.
  - A **note** under the field says "Valid JSON." or where and why it isn't ("Invalid JSON at line 2, column 7:
    expected ":"."); a lone number or string gets the server's own "Enter a JSON object or array.". JSON nested past
    the server's limit gets "The JSON is nested too deeply at line 1, column 129: the limit is 128 levels.", at the
    bracket that goes over: the widget writes the limit on the textarea (`data-dynamic-configs-json-max-depth`), so
    the script never has its own copy. An empty field gets no note.
  - **Colours:** a copy of the text, built only with `textContent`, sits behind the textarea, whose own text is made
    transparent. Keys, strings, numbers, `true`/`false`/`null` and punctuation each have a colour, and the token where
    the JSON breaks is underlined. The script copies the textarea's font, padding and size onto the copy and follows
    its scrolling and resizing; if a stylesheet overrides those styles on the copy, or the two differ in height once
    the textarea scrolls, the colours turn off and the plain textarea shows. Without `admin.css` the colours never
    start, and Format and the note still work.
  - The colours are custom properties (`--dynamic-configs-json-key`, `-string`, `-number`, `-literal`,
    `-punctuation`, `-error`) that a project can set in its own admin stylesheet. The light set has at least 4.5:1
    contrast on white; the dark set follows `prefers-color-scheme`, and Django's admin theme toggle (`data-theme`)
    overrides either way, as in Django's own admin CSS.
  - The script never parses values: it tokenizes the text and rebuilds it token by token, so integers too large for
    JavaScript (`12345678901234567890`) keep their exact text, and edits go through the browser's undo. Saving stores
    numbers as Python's `json` reads them: integers exactly, other numbers as floats, so `1.10` is saved as `1.1`. The checker uses a stack, not recursion, so deep nesting can't overflow it. (django-prettyjson and
    django-json-widget were considered and dropped: both re-encode the value through JavaScript numbers, which rounds
    large integers, and the second also blocks a strict Content Security Policy with inline scripts.)
- **List editor:** list and set values (`AdminListEditorWidget`) get `list_editor.js` and `admin.css`, in place of a
  textarea with one item per line, which couldn't hold an item's exact text (spaces at the ends, empty items, line
  breaks) and gave no help entering items of richer types:
  - **The item editor** is the item type's own input, as a single config of that type shows it: a number's text box,
    the date picker, a datetime's date, time and zone, `money_currency`'s amount and currency, a custom type's own
    widget. So every type, custom ones included, works with no code of its own. Beside it, one button reads **Add**
    when no item is selected and **Update** when one is; **Clear** empties the editor, deselects the list and turns
    the button back to Add.
  - **The list** is a `<select>` showing each item's stored text, which is also the item's line in raw mode, so
    switching between the two never looks like a change. Selecting an item loads it into the editor, and the button
    reads Update while it's edited; selecting another item drops an unfinished edit. **Remove**, **Up** and **Down**
    act on the selected item (one at a time; disabled with nothing selected, and Up and Down at the ends). **Sort**
    orders the list by value (see List and set types) and flips direction on each click; it's shown only when the
    item type can be sorted (see Custom types). Sets have no Up, Down or Sort, since they're unordered.
  - **Add and Update** have the server check the editor's value with the item type's real form field. A failure
    shows the type's own error under the editor and leaves the list untouched. Nothing is judged beyond the type's
    own check: an empty input is an empty item for `str` and `text`, and spaces follow `STRIP_STRINGS`. Sets reject
    a repeat ("That's already in the set."), compared after parsing.
  - **Raw mode** (a link) swaps the editor and list for one textarea holding the whole list, one item per line, for
    pasting and bulk edits: pasted lines go wherever the cursor is. **Apply** has the server check every line; if all
    pass they become the list, otherwise raw mode stays open with each failing line's error. **Cancel** returns to
    the list unchanged. Every line is an item, blank ones included: what's pasted is what's saved, and checking it
    is the admin's job. So a stray blank line is easy to spot and remove, Apply then notes which lines were blank
    ("Lines 2 and 3 were blank, so they were added as blank items."). An empty textarea is an empty list. Raw mode
    refuses to open while an item contains a line break ("Item 3 contains a line break, so the list can't be shown
    one item per line. Edit it in the item editor."), since that item would come back as two, and while the list is
    one empty item ("The list is one empty item, which raw mode would show as no items. Edit it in the item
    editor.").
  - **Saving** submits the list exactly: a hidden input holds the items' stored texts as a JSON array, and a mode
    flag tells the server whether to read that or the raw textarea. The page as served says raw, so without
    JavaScript the field is the raw textarea (raw mode is the fallback); the script sets list mode when it takes
    over, and raw mode while raw mode is open, so saving with raw mode open saves its text, with line errors if any
    fail. Every item is checked again on save; the page's checks are a convenience. Save is stopped, with a warning,
    while the item editor holds an unfinished change, a selected item edited but not updated or a new value typed
    but not added: "You have an unsaved change to an item: click Update or Clear." (Applying it silently could save
    an item halfway through being changed; dropping it would lose work.) Raw mode won't open then either, for the same
    reason, and shows the same warning.
  - **The check URL** is `<admin>/dynamic_configs/config/list-item/<type key>/`, a view on `ConfigAdminMixin`. It's
    keyed by the list or set type, not the config, so the add page can use it before the config exists. It sits
    behind the admin's login and CSRF check, needs add or change permission on configs, takes only POSTs, answers
    JSON, and never saves. It serves four requests:
    - **check an item**: the editor's inputs and the current items (for a set's repeat check); returns the item's
      stored text, or the type's error;
    - **load an item**: a stored text; returns the value for each of the editor's inputs by name, which the page
      fills in;
    - **check raw lines**: the lines as a JSON array; returns the items, or every failing line's error;
    - **sort**: the items and a direction; returns them in order, or "These items can't be sorted.".
  - Checking on the server keeps one set of rules, the Python ones: rules in the script would duplicate them, could
    drift from them, and couldn't cover custom types or multi-part inputs. Each Add, Update, load, Apply or Sort is
    one quick request.
  - Loading fills in the editor's inputs rather than replacing its HTML, because Django's widget scripts (the date
    picker, the Now and Today links) attach to inputs when the page loads and wouldn't be on new ones. That covers
    every widget built from ordinary inputs, selects and checkboxes; a custom widget run entirely by its own script
    isn't supported in the item editor.
  - Every message from the server is put on the page as text, never HTML. If the check URL can't be reached, the page
    says "Couldn't check the item; try again." and changes nothing.
  - Only the config admin has the editor: the check URL belongs to it and its permissions. `TypedLineListField` in a
    project's own forms keeps the textarea, the raw format.
- **Unregistered type:** a row whose type is no longer registered shows its stored text read-only, with a message
  saying the type is missing from settings.
- Permissions are Django's standard add/change/delete/view permissions; the list editor's check URL needs add or
  change permission.

## Optional integrations

### django-simple-history

Opt-in: install `django-dynamic-configs[simple-history]` and add `"dynamic_configs.contrib.simple_history"` to
`INSTALLED_APPS` (with `"simple_history"`).

- The sub-app (label `dynamic_configs_simple_history`) registers `Config` with simple_history in that app, and ships
  the migration creating `HistoricalConfig`. Projects that don't install it never need simple_history.
- Its `admin.py` imports `dynamic_configs.admin` first (so `INSTALLED_APPS` order doesn't matter), then, when
  `REGISTER_ADMIN` is on, replaces the registration with `ConfigAdminMixin` + `SimpleHistoryAdmin`, adding the History
  button.
- Changes through `update`, `delete` and `get_or_create` are recorded too; the user comes from simple_history's
  `HistoryRequestMiddleware` when it's installed.
- Check `dynamic_configs.E101`: the sub-app is installed but `simple_history` isn't in `INSTALLED_APPS`.

## Test helpers

- **`dynamic_configs.test.override_configs(**values)`**: a context manager and decorator (for functions, methods and
  classes). Overridden values are returned by `get` and `get_or_create` (as `(value, False)`) without touching the
  cache or the database. Restored in a `finally` block. Built on `contextvars`, so overrides don't leak between
  threads or async tasks, and they propagate into the async variants. On a class, like `override_settings`, it covers
  the whole class: its `test*` methods, inherited ones included, and the setup and teardown hooks of unittest, Django
  and pytest (`setUp`, `setUpClass`, `setUpTestData`, `setup_method`, `setup_class` and their teardowns). A
  subclass's values win over a decorated base's; stacked on one class, the inner decorator wins, as on functions.
- **pytest plugin** (`dynamic_configs/test/pytest_plugin.py`, registered under the `pytest11` entry point): a
  `config_overrides` fixture whose `.set(**values)` applies overrides for the rest of the test, cleared at teardown.
  (It isn't named `dynamic_configs`, which would hide the module inside tests that also call `dynamic_configs.get`.)
  The plugin imports nothing from Django at load time.
- The plugin does not clear the project's cache between tests. The README tells projects to use `"CACHE": None` in
  test settings, or overrides.
- Django's `TestCase` never commits, so `on_commit` cache writes don't run there; tests that need them use
  `captureOnCommitCallbacks(execute=True)`.

## Documentation site

Hosted on Read the Docs, built with **Sphinx**:

- **MyST** so pages are written in Markdown; **autodoc** (with type hints) for the API reference, generated from the
  docstrings; the **Read the Docs theme** (sphinx-rtd-theme), for the layout readers know from other projects' docs
  (it has no dark mode). `docs/_static/custom.css` lets table cells wrap, which the theme turns off, so wide tables
  fit the page instead of scrolling sideways.
- Pages: Overview, Installation, Quick start, Reading and writing settings (the API), Types (built-in, list and set,
  custom, constraints as custom types), Worked example: the money types (writing a type, then extending it), Caching, Failure handling and logging, Admin and skins (including the JSON editor's colours and the list editor), simple-history,
  Testing, API reference, Changelog, and Development (contributing, running tox, this design document).
- `.readthedocs.yaml` pins the build (Python version, the package plus `docs/requirements.txt`, `fail_on_warning: true`).
- `tox -e docs` builds it locally with warnings as errors (`sphinx-build -W`), and CI runs it, so broken references
  or docstrings fail the build.
- Versioned docs: Read the Docs builds `latest` from `main` and a version per release tag.
- `conf.py` excludes `design/plans/` (implementation plans, kept locally and ignored by git) and the build directory,
  so they're never published.
- The Changelog page includes `CHANGELOG.md`, which follows [Keep a Changelog](https://keepachangelog.com/): an
  Unreleased section, then one section per version with Added, Changed, Deprecated, Removed, Fixed and Security
  headings as needed. 0.1.0 is the first release.
- The README stays short: what it is, installation, a quick start and a link to the docs. The reference material the
  README held while there was no docs site (the JSON editor's colours, the list editor, `STRIP_STRINGS`, a custom
  `form` and `raw_help_text` in the list editor, known limitations) moves to Admin and skins, and its Development
  section (virtual environment, browser, tests, tox and the umask note) to Development.

## Package layout

The `src/` layout, so tests run against the installed package. Modules mirror Django's layout.

```
pyproject.toml   tox.ini   MANIFEST.in   LICENSE   README.md   CHANGELOG.md   .readthedocs.yaml
.github/workflows/ci.yml   .github/workflows/release.yml
docs/
    conf.py   index.md   (one .md per page listed under Documentation site)
    design/django-dynamic-configs.md
src/dynamic_configs/
    __init__.py         lazy public API
    api.py              get, get_or_create, update, delete, async variants
    cache.py            cache access and the missing marker
    conf.py             DYNAMIC_CONFIGS with defaults
    checks.py           system checks
    exceptions.py
    log.py              logging helper with the re-entrancy guard
    _overrides.py       overrides for the current context (read by the API, set by the test helpers)
    models.py           Config, ConfigDoesNotExist
    signals.py          post_save / post_delete cache handling
    admin.py            ConfigAdminMixin (with the list editor's check URL), ConfigAdmin, AdminZonedDateTimeWidget,
                        AdminJSONTextarea, AdminListEditorWidget
    apps.py
    static/dynamic_configs/
        admin.js        the admin's optional script (type step, time zones)
        json_editor.js  the admin's JSON editor
        list_editor.js  the admin's list editor
        admin.css       the editors' layout, and the JSON editor's colours
    types/
        base.py         ConfigType: a type's definition, type check and text conversion
        registry.py     registry build, lookup, list and set variants
        builtin.py      built-in type definitions
        serializers.py  built-in serializers
        money.py        Money, MoneySerializer, MoneyCurrencySerializer, by_currency_then_amount (example types, not
                        registered by default)
    forms/
        list.py         LineListField, TypedLineListField (a list of stored texts, or one item per line)
        json.py         JSONTextField, JSONTextarea
        datetime.py     ZonedDateTimeField, ZonedDateTimeWidget, datetime_field
        fields.py       SerializerField, DurationUnitField, formfield_for
        money.py        MoneyField, MoneyCurrencyField
        config.py       ConfigTypeForm, ConfigAddForm, add_form_for, ConfigChangeForm, change_form_for (the admin's model forms)
    test/
        __init__.py     override_configs
        pytest_plugin.py
    migrations/
    contrib/simple_history/
        apps.py   models.py   admin.py   checks.py   migrations/
    py.typed
tests/
    settings.py   conftest.py   then a mirror of src/dynamic_configs/
    browser/      the admin's scripts in Chromium, Firefox and WebKit (Playwright), with a small test app
                  (models with zoned datetimes and an inline)
```

## Packaging and tooling

- **setuptools** through `pyproject.toml` (no `setup.py`). Distribution `django-dynamic-configs`, import package
  `dynamic_configs`, initial version `0.1.0`, `Development Status :: 3 - Alpha`. License: MIT, "Copyright (c) 2026
  Tecktron". Author: `Tecktron` (name only, no email).
- `requires-python = ">=3.10"`; dependency `Django>=5.2`. Classifiers for Django 5.2, 6.0, 6.1 and each supported
  Python.
- Extra: `simple-history` (`django-simple-history>=3.8`, the first release supporting Django 5.2; 3.11 added
  Django 6.0, and pip resolves the newest release anyway).
- Package data: `py.typed` and the static files (`static/dynamic_configs/*.js` and `*.css`); the suite checks they
  are found, which under tox (installing the built wheel) checks they're packaged.
- The sdist also carries the whole test suite, `CHANGELOG.md` and `tox.ini` (`MANIFEST.in`), so the package can be
  tested where it's built from the sdist; without it, setuptools picks up only `tests/test*.py`, which can't run
  without `tests/settings.py`. The wheel holds only the package.
- Project URLs: Homepage, Documentation (Read the Docs), Source, Issues and Changelog (`CHANGELOG.md` on GitHub).
- Development dependencies in `requirements.txt`: an editable install of the package plus coverage, pytest,
  pytest-django, pytest-mock (tests patch with its `mocker` fixture, not `unittest.mock`), pytest-playwright (the
  browser tests), ruff and tox, installed into a `venv/` in the repository (ignored by git). The browser tests need
  a browser, installed into the virtualenv's Playwright package: Chromium, which they use by default, with
  `PLAYWRIGHT_BROWSERS_PATH=0 venv/bin/playwright install --only-shell chromium`, and Firefox or WebKit
  (`install firefox`, `install webkit`) to run them there with `--browser`. The documentation tools
  (sphinx, myst-parser, sphinx-rtd-theme, sphinx-autodoc-typehints) go in `docs/requirements.txt`, which `requirements.txt`
  includes and Read the Docs installs.
- `pytest11` entry point: `dynamic_configs = "dynamic_configs.test.pytest_plugin"`.
- Type hints throughout, with `py.typed`.
- Ruff: 120 columns, double quotes, `target-version = "py310"`; rules `E, F, UP, B, S, C4, N, DJ, PT, I, PTH, D`
  (`D` is pydocstyle with the `pep257` convention, so a missing docstring fails lint), ignoring `E501` and `DJ001`
  (`value` is deliberately a nullable `TextField`: `NULL` is empty, distinct from `""`). isort: `force-wrap-aliases`
  and `split-on-trailing-comma`. In `tests/`, `S101`, `S105`, `S106`, `PT011` and `D` are ignored; `D` is also
  ignored in `migrations/`.

## Testing, coverage and CI

### tox environments

Pairs follow Django's support table:

| Django | Python                         |
|--------|--------------------------------|
| 5.2    | 3.10, 3.11, 3.12, 3.13, 3.14   |
| 6.0    | 3.12, 3.13, 3.14               |
| 6.1    | 3.12, 3.13, 3.14, 3.15         |

The matrix environments skip `tests/browser` (`--ignore`), since the scripts don't change with Python or Django.

Plus:
- `browser-{chromium,firefox,webkit}-django{52,61}`: six environments, one per browser engine on the oldest and
  newest Django (their admin markup differs: 5.2's time zone note doesn't name the zone and sits beside each input),
  on the newest Python; each runs `tests/browser` in its headless browser (`--browser <engine>`) with
  pytest-playwright, against pytest-django's live server, installing only that browser into the environment's
  Playwright package (`PLAYWRIGHT_BROWSERS_PATH=0`; Chromium as the headless shell, `--only-shell`). One engine per
  environment, so a failure names its browser and CI runs them in parallel. Without coverage, since the matrix holds
  the Python code to 100%. The browser tests
  run after all other tests in any run: Playwright keeps an event loop on the test thread until the session ends, so
  Django's async check (`DJANGO_ALLOW_ASYNC_UNSAFE`) is relaxed only from the first browser test on. All six are in
  plain `tox`'s list. Firefox and WebKit need system libraries a machine may lack, and fail without them: locally,
  `tox --skip-env browser-webkit` leaves WebKit out, and the development guide gives a recipe that runs the WebKit
  environments in Playwright's Docker image (`mcr.microsoft.com/playwright/python`, non-root, `--ipc=host`, with a
  `base_python` override for the image's Python 3.12).
- `extras`: newest Django and Python, with django-simple-history installed and its app enabled in the test settings
  (`tests/settings.py` reads an environment variable).
- `postgres`: newest Django and Python against PostgreSQL, with `psycopg[binary]`; `tests/settings.py` switches to
  PostgreSQL when an environment variable says so, and the connection comes from libpq's standard `PG*` variables,
  which tox passes through. Every other environment, and every local run, uses SQLite: the package's ORM use is
  plain, so this checks that it installs, migrates and runs on the database most projects use (and runs `update`'s
  row lock for real, which SQLite ignores).
- `redis`, `redis-json` and `memcached`: the suite against a real cache server instead of LocMemCache, chosen by
  `DYNAMIC_CONFIGS_TEST_CACHE` in `tests/settings.py` (helpers in `tests/real_cache.py`): Django's `RedisCache` (newest
  Django, `redis`); django-redis with its JSON serializer (Django 6.0, the newest django-redis supports); Django's
  `PyMemcacheCache` (newest Django, `pymemcache`); all on the newest Python. The address comes from
  `DYNAMIC_CONFIGS_TEST_REDIS_URL` or `DYNAMIC_CONFIGS_TEST_MEMCACHED`, passed through by tox, with no default: the
  suite empties the cache around every test (`FLUSHDB`, or a full Memcached flush), and a default of the standard local
  address could erase another project's data. An unknown value, or a missing address, is an error when the settings
  load. Before the first test, `pytest_sessionstart` in `tests/conftest.py` stops the run, deleting nothing, if
  another run holds the address's lock (a file in the temporary directory named from a hash of the address, locked
  with `flock` until the process exits; not on Windows, which has no `fcntl`), or the server already holds data
  (Redis's `DBSIZE` for the URL's database, Memcached's `curr_items`), or can't be reached. A running suite keeps the
  server empty between tests, so the emptiness check alone can't see a second run; the lock can.
  The test database is a file-backed SQLite one, so a second process can share it. `tests/test_real_cache.py` checks
  that each environment really uses its server (the backend's class, an entry read back with the server's own client,
  the JSON serializer's lists) and that a 255-character name is cached there.
- `djangomain`: Django's main branch on the newest Python; non-blocking in CI.
- `lint`: ruff check and format check.
- `docs`: builds the documentation site with warnings as errors.
- `coverage`: combines every environment's data and enforces the threshold.

Plain `tox` runs the matrix, the browser environments, `extras`, `lint`, `docs` and `coverage`. `postgres` (it needs a
PostgreSQL server), `redis`, `redis-json` and `memcached` (each needs a server of its own) and `djangomain` (it installs
Django from GitHub each time) run only when named (`tox -e postgres`), and always in CI.

### Coverage

Configured in `pyproject.toml`:

- `branch = true`, measuring only the `dynamic_configs` package; `migrations/` is omitted. Each tox environment writes
  its own data file (`COVERAGE_FILE`), which the `coverage` environment combines.
- Tests run under `coverage run -m pytest`, not pytest-cov: pytest imports this package's pytest plugin at startup,
  before pytest-cov would start measuring, so the plugin's module-level code would show as uncovered.
- `[tool.coverage.paths]` maps the installed `site-packages/dynamic_configs` back to `src/dynamic_configs`, so data
  from every tox environment combines.
- **100% branch coverage is enforced on the combined data** (`fail_under = 100`), not per environment, because
  some lines only run with or without the extras. `show_missing = true`.
- Locally, `tox` does the same: the `coverage` environment combines what the other environments recorded and enforces
  100%. A single `coverage run -m pytest` in the development virtual environment is a quick check, and its report can
  be under 100% (the lines that need the extras, or their absence).
- `# pragma: no cover` is not used. `if TYPE_CHECKING:` blocks are excluded in config (`exclude_also`).
- Our code includes the pytest plugin (tested with pytest's `pytester`), the test helpers and `contrib/`.

### GitHub Actions

- **`ci.yml`**, on pushes and pull requests:
  - `lint` and `docs` jobs.
  - `package` job: builds the sdist and wheel and runs `twine check --strict`, the same as `release.yml`'s build, so
    a packaging problem shows up on the pull request rather than after a tag is pushed.
  - `browser` job, a matrix of engine (`chromium`, `firefox`, `webkit`) by Django (`52`, `61`), running
    `browser-<engine>-django<version>`: installs that browser with `playwright install --with-deps <engine>`
    (`--only-shell` for Chromium; `--with-deps` adds the system libraries through the runner's `sudo`), then runs
    the environment.
  - `test` job: a matrix over the tox environments; each saves its coverage data as an artifact. The `postgres`
    environment runs with a PostgreSQL service container; `redis` and `redis-json` with a Redis one (`redis:8`), and
    `memcached` with a Memcached one (`memcached:1.6`), each job with a server of its own. `djangomain` uses
    `continue-on-error`.
  - `coverage` job: after `test`; combines the artifacts, prints the report (with any missing lines), fails under
    100%, and saves the HTML report as an artifact to download. No coverage service: the 100% rule already blocks any
    drop, and the job's log names the missing lines.
- **`release.yml`**, on pushing a `v*` tag: checks the tag matches the package version, builds the sdist and wheel,
  and publishes to PyPI through trusted publishing (environment `pypi`, `id-token: write`), so no token is stored.
  Also runnable by hand (`workflow_dispatch`) as a dry run: the tag check is skipped, `version` is rewritten in the
  runner's copy to `<version>.dev<run number>` (nothing is committed), and a separate job publishes to TestPyPI
  through the `testpypi` environment. Each publish job is guarded by its trigger (`pypi` only for a `v*` tag push,
  `testpypi` only for a manual run), so a manual run can't reach PyPI nor a tag TestPyPI.

## README

Short: what the package is, installation, a quick start, and a link to the documentation site.

Badges: CI status, coverage (a static "coverage 100%" badge, which stays true because CI fails below 100%),
documentation build (Read the Docs), PyPI version, supported Python versions, supported Django versions, license.

### One-time setup outside the repo (maintainer)

- **PyPI:** before the first release, on pypi.org, *Your account → Publishing → Add a pending publisher*: project
  `django-dynamic-configs`, owner `Tecktron`, repository `django-dynamic-configs`, workflow `release.yml`, environment
  `pypi`. The PyPI badges show "not found" until the first release.
- **TestPyPI:** for the dry run, create an account on test.pypi.org with 2FA, then *Your account → Publishing → Add a
  pending publisher*: project `django-dynamic-configs`, owner `Tecktron`, repository `django-dynamic-configs`,
  workflow `release.yml`, environment `testpypi`.
- **GitHub:** create the `pypi` environment in the repository settings. Under *Deployment branches and tags*, choose
  *Selected branches and tags* and add a rule of ref type *Tag* for `v*`: a release runs from a tag, and *Protected
  branches only* lets only protected branches deploy, so it would block the release. Optionally, add required
  reviewers, so each release waits for approval.
- **GitHub (dry run):** create the `testpypi` environment, with a deployment rule (*Selected branches and tags*) that
  allows the branch `main`.
- **Read the Docs:** sign in at readthedocs.org with GitHub and import `Tecktron/django-dynamic-configs`. Its GitHub
  integration starts a build on every push, and the docs badge starts working; if a push to `main` doesn't start a
  build, check the integration in the project's *Admin → Integrations*. Then, in *Admin → Automation Rules*, add a
  rule that activates new versions for tags matching SemVer (or `v*`); without it, Read the Docs doesn't build
  release tags.
