# Installation

django-dynamic-configs needs Python 3.10 or later and Django 5.2 or later.

Install it from PyPI:

```
pip install django-dynamic-configs
```

Add it to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.admin",
    "dynamic_configs",
]
```

Then create its table (`dynamic_configs_config`):

```
python manage.py migrate
```

The admin is registered automatically when `django.contrib.admin` is installed (see [Admin and skins](admin.md)).

## The simple-history extra

To record every change with [django-simple-history](https://django-simple-history.readthedocs.io/), install the
extra:

```
pip install "django-dynamic-configs[simple-history]"
```

It needs a further app in `INSTALLED_APPS` and its own migration; see [simple-history](simple-history.md). Projects
that don't install it never need simple_history.

## Configuration

Everything is set in one optional dict in your Django settings. These are the keys and their defaults:

```python
DYNAMIC_CONFIGS = {
    "CACHE": "default",       # cache alias, or None to disable caching
    "TIMEOUT": 300,           # cache timeout in seconds; None = no expiry
    "TYPES": {},              # custom types
    "REGISTER_ADMIN": True,   # register ConfigAdmin automatically
    "STRIP_STRINGS": None,    # spaces at the ends of strings typed in the admin
}
```

All keys are optional, and the setting itself can be left out. The settings are re-read when `DYNAMIC_CONFIGS`
changes, so `override_settings` works in tests.

### `CACHE`

The alias of the cache in `CACHES` that holds settings. `None` turns caching off, and so does a `DummyCache` backend.
See [Caching](caching.md).

### `TIMEOUT`

How long a cached setting is kept, in whole seconds (0 or more). `None` means no expiry, as in Django.

### `TYPES`

Custom types, keyed by type key. See [Custom types](types.md#custom-types).

### `REGISTER_ADMIN`

Whether to register `ConfigAdmin` on the admin site. Set it to `False` to register the admin yourself, for example
with an admin skin's base class (see [Admin skins](admin.md#admin-skins)).

### `STRIP_STRINGS`

Whether the admin strips spaces from the ends of strings typed in a single-line input: `str` values, the items of
`list:str` and `set:str`, and custom types without a `form` (which get a plain text input). The package makes no
judgement about such spaces; the default is a sensible middle, and you can choose either way:

| `STRIP_STRINGS`   | A single value | List and set items (item editor and raw mode)                  |
|-------------------|----------------|----------------------------------------------------------------|
| `None` (default)  | stripped       | kept exactly                                                   |
| `True`            | stripped       | stripped (so in a set, `" a"` and `"a"` are the same item)     |
| `False`           | kept exactly   | kept exactly                                                   |

It applies to the admin only: values set from code are always stored exactly. Config names are always stripped (a
name is an identifier, not a value), and `text` values and descriptions are always kept exactly.

## System checks

Django's system checks (`manage.py check`, and every `runserver` and `migrate`) report mistakes in the configuration
at startup:

| Check                   | Reported when                                                            |
|-------------------------|--------------------------------------------------------------------------|
| `dynamic_configs.E001`  | `DYNAMIC_CONFIGS` or `TYPES` has the wrong shape, an unknown or invalid key, an entry missing `type` or `serializer`, an entry with both `sort_key` and `sort_compare` or one that isn't callable, or a setting has the wrong kind of value (for example `STRIP_STRINGS` isn't `True`, `False` or `None`) |
| `dynamic_configs.E002`  | a dotted path in `TYPES` can't be imported                               |
| `dynamic_configs.E003`  | a serializer can't be created with no arguments, or lacks a callable `serialize` or `deserialize` |
| `dynamic_configs.E004`  | a `form` isn't a `django.forms.Field` subclass                           |
| `dynamic_configs.E005`  | `CACHE` names an alias that isn't in `CACHES`                            |
| `dynamic_configs.W001`  | (warning) an admin using `ConfigAdminMixin` sets options the mixin ignores; see [Admin and skins](admin.md) |
| `dynamic_configs.E101`  | the simple-history integration is installed without `simple_history`; see [simple-history](simple-history.md) |

Checks don't run under every server (gunicorn and uwsgi don't run them), so a broken `TYPES` entry never stops
settings being read: it's logged as an error and skipped, and only settings of that type are affected (they read as
unregistered; see [Failure handling and logging](failures.md)).
