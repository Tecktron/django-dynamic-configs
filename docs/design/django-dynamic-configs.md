# django-dynamic-configs: design

Status: draft for review, 2026-11-02.

## Purpose

A reusable, public Django app for runtime configuration: typed values that can be **added** and edited in the Django
admin, and read from code through a small, cached API. It replaces hand-rolled per-project settings models.

### Goals

- Admins can add, edit and delete settings; each has a unique name, a type, a value and an optional description.
- A clean programmatic API: `get`, `get_or_create`, `update`, `delete`, plus async variants.
- Typed values, including list and set variants of every single-line type, and custom types declared in Django
  settings.
- Nothing an admin enters is ever imported, evaluated or executed. Types come only from code.
- Cached reads when a cache is configured; a caller that passes a default is never broken by an outage.
- Works under admin skins (jazzmin, grappelli, unfold) by using stock admin pages.
- Optional, explicit integrations: django-simple-history and django-prettyjson. Neither is required.
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
| `datetime` | Date and time  | `datetime`         | ISO 8601 (see Datetimes and time zones)      | `SplitDateTimeField` + admin widget   |
| `json`     | JSON           | `dict` or `list`   | `json.dumps(value, ensure_ascii=False)`      | `JSONTextField` (see below)           |
| `seconds`  | Seconds        | `timedelta`        | the number of seconds (`"90"`, `"1.5"`)      | `DurationUnitField("seconds")`        |
| `minutes`  | Minutes        | `timedelta`        | the number of minutes                        | `DurationUnitField("minutes")`        |
| `hours`    | Hours          | `timedelta`        | the number of hours                          | `DurationUnitField("hours")`          |
| `days`     | Days           | `timedelta`        | the number of days                           | `DurationUnitField("days")`           |
| `weeks`    | Weeks          | `timedelta`        | the number of weeks                          | `DurationUnitField("weeks")`          |

Durations are per-unit types, which are clearer for admins than a free-form duration syntax: the admin enters `1.5`
for an `hours` setting and code reads `timedelta(hours=1.5)`. Numbers are written without a trailing `.0` (`"2"`, not
`"2.0"`).

Every type, built-in or custom, has a short `help_text` describing its text format (for example "YYYY-MM-DD" for
`date`, "one number of hours, e.g. 1.5" for `hours`), shown as the value's help on the admin's add and change pages.

`JSONTextField` is a textarea showing the value pretty-printed (`indent=2`), validated on the server. When
`"prettyjson"` is in `INSTALLED_APPS`, it uses `prettyjson.widgets.PrettyJSONWidget` instead of the plain textarea.

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
- The admin's date and time widgets already interpret input in the current time zone, so admin input follows the same
  rules.

### List and set types

Every type whose registry entry has `listable=True` gets a list variant, keyed `list:<key>` and labelled
`List of <label>`. If its Python type is also hashable, it gets a set variant too, keyed `set:<key>` and labelled
`Set of <label>`. Built-ins are listable except `text` (items could contain newlines) and `json` (already a
structure); every listable built-in is hashable, so each gets both variants.

- Python type: a `list` of the item type, or a `frozenset` for set types (read-only, and usable as a dict key or in
  comparisons).
- Stored text: a JSON array of each item's serialized string, e.g. `["1", "2"]` for `list:int`. Set types keep the
  order the items were first entered, so the admin page doesn't reshuffle them. Custom types get the same treatment
  through their own serializer.
- Form field: `TypedLineListField(item_type, unique=False)` (`dynamic_configs/forms/list.py`), a textarea with one
  item per line. Blank lines are ignored, each line is stripped and run through the item serializer's `deserialize`,
  and an error names the line ("Line 3: …"). Set types use `unique=True`: duplicates (compared after `deserialize`,
  so `1` and `01` match for `set:int`) are rejected with an error naming the lines ("Lines 2 and 5 are the same"),
  not dropped silently. It is a typed variant of `LineListField`, an untyped one-item-per-line field in the same
  module.

### Custom types

Declared in Django settings; every value is a dotted path except `label`, `help_text` and `listable`:

```python
DYNAMIC_CONFIGS = {
    "TYPES": {
        "color": {
            "type": "myapp.colors.Color",                 # required
            "serializer": "myapp.colors.ColorSerializer",  # required
            "form": "myapp.forms.ColorField",              # optional: a django.forms.Field subclass
            "label": "Color",                              # optional, defaults to the key
            "help_text": "A hex color, e.g. #1a2b3c",      # optional, defaults to ""
            "listable": True,                              # optional, defaults to True: list and set variants
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
            "help_text": "An amount with at most 2 decimal places and a 3-letter currency code, e.g. 9.99 CAD",
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
| `dynamic_configs.E001`  | `DYNAMIC_CONFIGS` or `TYPES` has the wrong shape, an invalid key, or an entry missing `type`/`serializer` |
| `dynamic_configs.E002`  | a dotted path can't be imported                                          |
| `dynamic_configs.E003`  | a serializer lacks a callable `serialize` or `deserialize`               |
| `dynamic_configs.E004`  | `form` is not a `django.forms.Field` subclass                            |
| `dynamic_configs.E005`  | `CACHE` names an alias that isn't in `CACHES`                            |

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
}
```

All keys are optional. Settings are read through `dynamic_configs/conf.py`, which applies the defaults and is reset on
`setting_changed`.

## Admin

The admin ships **no templates or CSS** of its own; it uses stock `ModelAdmin` pages, so admin skins apply. Its one
script, `dynamic_configs/admin.js`, is optional: it only fills in defaults and saves clicks, and every page works
without it. Projects can still override the standard templates (`admin/dynamic_configs/config/change_form.html`).

- **`ConfigAdminMixin`** holds all the behaviour. **`ConfigAdmin`** is `ConfigAdminMixin` + `admin.ModelAdmin`, and is
  registered automatically by `dynamic_configs.admin.register_admin()` unless `REGISTER_ADMIN` is `False`; calling it
  again does nothing, so integrations can rely on it. Skins with their own base class (unfold) unregister it and
  register `ConfigAdminMixin` + their `ModelAdmin`.
- **List page:** name, type label, a value preview (list and set items joined with `, `, long values truncated), description
  and modified time. Search on name and description; filter by type.
- **Add page:** two steps, so the value can use its type's own field. The first step asks only for the type (a
  select of registered types, including list and set variants); Save moves to the second step at
  `add/?type=<key>`, which shows the name, the type (read-only), the value in its type's form field, `allow_null` and
  the description, as on the change page. With the admin script, choosing a type moves on without clicking Save. An
  unknown `?type=` shows the first step again, and other query parameters (a popup's, say) are kept. A boolean gets
  the yes/no/unknown choice on this page, since whether the config allows None isn't known until it's saved.
- **Change page:** name and type are read-only; the value uses its type's form field (checkbox, date picker, one item
  per line, and so on).
- On both pages, an empty value is saved as `None` when `allow_null` is set. When it isn't set, an empty value is the
  empty string for `str` and `text`, an empty list or set for list and set types, and a "required" error for every
  other type. (So
  a `str` setting with `allow_null` can't hold the empty string through the admin; code can still `update` it to `""`.)
- **Whitespace:** on both pages the name and `str` values are stripped, as is any value whose type is edited in a
  single-line text input (custom types without a `form`, for example). `text` values and descriptions are kept exactly
  as typed.
- **Widgets:** Django's plain date, split date/time and textarea widgets are swapped for the admin's versions (date
  picker, styled textarea), keeping their attributes. A type's own widget is never replaced, even one built on
  `Textarea`.
- **Unregistered type:** a row whose type is no longer registered shows its stored text read-only, with a message
  saying the type is missing from settings.
- Permissions are Django's standard add/change/delete/view permissions.

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

### django-prettyjson

Optional: when `"prettyjson"` is in `INSTALLED_APPS`, the `json` type's form uses `PrettyJSONWidget`. The package is
not a dependency (its last release was 2018). Its viewer escapes keys and values, so stored JSON can't inject script
into the admin. Installable with `django-dynamic-configs[prettyjson]`.

## Test helpers

- **`dynamic_configs.test.override_configs(**values)`**: a context manager and decorator (for functions, methods and
  classes). Overridden values are returned by `get` and `get_or_create` (as `(value, False)`) without touching the
  cache or the database. Restored in a `finally` block. Built on `contextvars`, so overrides don't leak between
  threads or async tasks, and they propagate into the async variants.
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
  docstrings; the **furo** theme.
- Pages: Overview, Installation, Quick start, Reading and writing settings (the API), Types (built-in, list and set,
  custom, constraints as custom types), Worked example: the money types (writing a type, then extending it), Caching, Failure handling and logging, Admin and skins, simple-history, prettyjson,
  Testing, API reference, Changelog, and Development (contributing, running tox, this design document).
- `.readthedocs.yaml` pins the build (Python version, the package plus `docs/requirements.txt`, `fail_on_warning: true`).
- `tox -e docs` builds it locally with warnings as errors (`sphinx-build -W`), and CI runs it, so broken references
  or docstrings fail the build.
- Versioned docs: Read the Docs builds `latest` from `main` and a version per release tag.
- The README stays short: what it is, installation, a quick start and a link to the docs.

## Package layout

The `src/` layout, so tests run against the installed package. Modules mirror Django's layout.

```
pyproject.toml   tox.ini   LICENSE   README.md   CHANGELOG.md   .readthedocs.yaml
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
    admin.py            ConfigAdminMixin, ConfigAdmin
    apps.py
    static/dynamic_configs/admin.js   the admin's optional script
    types/
        base.py         ConfigType: a type's definition, type check and text conversion
        registry.py     registry build, lookup, list and set variants
        builtin.py      built-in type definitions
        serializers.py  built-in serializers
        money.py        Money, MoneySerializer, MoneyCurrencySerializer (example types, not registered by default)
    forms/
        list.py         LineListField, TypedLineListField
        json.py         JSONTextField
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
```

## Packaging and tooling

- **setuptools** through `pyproject.toml` (no `setup.py`). Distribution `django-dynamic-configs`, import package
  `dynamic_configs`, initial version `0.1.0`, `Development Status :: 3 - Alpha`. License: MIT, "Copyright (c) 2026
  Tecktron". Author: `Tecktron` (name only, no email).
- `requires-python = ">=3.10"`; dependency `Django>=5.2`. Classifiers for Django 5.2, 6.0, 6.1 and each supported
  Python.
- Extras: `simple-history` (`django-simple-history>=3.8`, the first release supporting Django 5.2; 3.11 added
  Django 6.0, and pip resolves the newest release anyway) and `prettyjson` (`django-prettyjson>=0.4.1`).
- Development dependencies in `requirements.txt`: an editable install of the package plus coverage, pytest,
  pytest-django, ruff and tox, installed into a `venv/` in the repository (ignored by git). The documentation tools
  (sphinx, myst-parser, furo, sphinx-autodoc-typehints) go in `docs/requirements.txt`, which `requirements.txt`
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

Plus:
- `extras`: newest Django and Python, with django-simple-history and django-prettyjson installed and their apps
  enabled in the test settings (`tests/settings.py` reads an environment variable).
- `postgres`: newest Django and Python against PostgreSQL (CI service container); every other environment uses SQLite.
- `djangomain`: Django's main branch on the newest Python; non-blocking in CI.
- `lint`: ruff check and format check.
- `docs`: builds the documentation site with warnings as errors.
- `coverage`: combines every environment's data and enforces the threshold.

### Coverage

Configured in `pyproject.toml`:

- `branch = true`, `parallel = true`, measuring only the `dynamic_configs` package; `migrations/` is omitted.
- Tests run under `coverage run -m pytest`, not pytest-cov: pytest imports this package's pytest plugin at startup,
  before pytest-cov would start measuring, so the plugin's module-level code would show as uncovered.
- `[tool.coverage.paths]` maps the installed `site-packages/dynamic_configs` back to `src/dynamic_configs`, so data
  from every tox environment combines.
- **100% branch coverage is enforced on the combined data** (`fail_under = 100`), not per environment, because
  some lines only run with or without the extras. `show_missing = true`.
- `# pragma: no cover` is not used. `if TYPE_CHECKING:` blocks are excluded in config (`exclude_also`).
- Our code includes the pytest plugin (tested with pytest's `pytester`), the test helpers and `contrib/`.

### GitHub Actions

- **`ci.yml`**, on pushes and pull requests:
  - `lint` and `docs` jobs.
  - `test` job: a matrix over the tox environments; each saves its coverage data as an artifact. The `postgres`
    environment runs with a PostgreSQL service container. `djangomain` uses `continue-on-error`.
  - `coverage` job: after `test`; combines the artifacts, fails under 100%, writes `coverage.xml` and uploads it to
    Codecov using GitHub's OIDC identity (`use_oidc: true`, `id-token: write`), so no token is stored.
- **`release.yml`**, on pushing a `v*` tag: checks the tag matches the package version, builds the sdist and wheel,
  and publishes to PyPI through trusted publishing (environment `pypi`, `id-token: write`), so no token is stored.

## README

Short: what the package is, installation, a quick start, and a link to the documentation site.

Badges: CI status, Codecov coverage, documentation build (Read the Docs), PyPI version, supported Python versions,
supported Django versions, license.

### One-time setup outside the repo (maintainer)

- **Codecov:** sign in at codecov.io with GitHub and give the Codecov app access to
  `Tecktron/django-dynamic-configs`. No token is needed.
- **PyPI:** before the first release, on pypi.org, *Your account → Publishing → Add a pending publisher*: project
  `django-dynamic-configs`, owner `Tecktron`, repository `django-dynamic-configs`, workflow `release.yml`, environment
  `pypi`. The PyPI badges show "not found" until the first release.
- **GitHub:** create the `pypi` environment in the repository settings (optionally requiring approval before a
  release runs).
- **Read the Docs:** sign in at readthedocs.org with GitHub and import `Tecktron/django-dynamic-configs`. Builds then
  run on every push, and the docs badge starts working.
