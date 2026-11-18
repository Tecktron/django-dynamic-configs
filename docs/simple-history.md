# simple-history

An optional integration with [django-simple-history](https://django-simple-history.readthedocs.io/) records every
change to every setting, and adds the History button to the config admin, from which a past version can be viewed
and restored. It's opt-in: projects that don't install it never need simple_history.

## Setting it up

Install the package with the `simple-history` extra, which installs django-simple-history 3.8 or later:

```
pip install "django-dynamic-configs[simple-history]"
```

Add both `"simple_history"` and the integration to `INSTALLED_APPS`. Their order, and their order relative to
`"dynamic_configs"`, doesn't matter:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.admin",
    "dynamic_configs",
    "simple_history",
    "dynamic_configs.contrib.simple_history",
]
```

To record which user made each change, add simple_history's middleware too:

```python
MIDDLEWARE = [
    # ...
    "simple_history.middleware.HistoryRequestMiddleware",
]
```

Then create the history table:

```
python manage.py migrate
```

The integration is its own app, labelled `dynamic_configs_simple_history`. It registers `Config` with simple_history
in that app, and ships the migration that creates the historical model, `HistoricalConfig`.

The shipped migration assumes simple_history's defaults for the settings that shape the historical model:

- `SIMPLE_HISTORY_HISTORY_ID_USE_UUID` (a UUID `history_id`) isn't supported. The migration creates integer ids, so
  every config save would fail. The system check `dynamic_configs.E102` reports it.
- `SIMPLE_HISTORY_DATE_INDEX` set to `False` or `"Composite"` changes the index on `history_date`, and
  `SIMPLE_HISTORY_HISTORY_CHANGE_REASON_USE_TEXT_FIELD` makes `history_change_reason` a text field. Either leaves a
  pending migration in `dynamic_configs_simple_history`, which `makemigrations` would write into this package. Leave
  them at their defaults, or give the app a migrations package of your own with `MIGRATION_MODULES`: copy the shipped
  `0001_initial.py` into it and run `makemigrations`. You then follow this package's later migrations yourself.

## What's recorded

Every change is recorded, whether it's made in the admin or through the API: `get_or_create` creating a setting,
`update`, and `delete`. With `HistoryRequestMiddleware` installed, a change made during a request records the user.

Like the cache, the history is kept through Django's model signals, so `QuerySet.update()`, `bulk_create()` and
`bulk_update()` aren't recorded.

## The admin

When `DYNAMIC_CONFIGS["REGISTER_ADMIN"]` is on (the default), the integration replaces the config admin with
`ConfigHistoryAdmin`: `ConfigAdminMixin` combined with simple_history's `SimpleHistoryAdmin`. Each setting's page gets
a **History** button, listing its past versions; opening one shows that version in the setting's own input (the list
editor for a list, say), and saving it restores it.

A config's type never changes: a version whose type isn't the config's type (changed in the database since), or
isn't registered, isn't restored, and the History page says why.

If you register the admin yourself (`"REGISTER_ADMIN": False`, see
[Customizing the admin](admin.md#customizing-the-admin)), use `ConfigHistoryAdmin`, or combine `ConfigAdminMixin`
with `SimpleHistoryAdmin` and your skin's base class (the order is shown in
[Admin skins](admin.md#admin-skins)):

```python
from django.contrib import admin

from dynamic_configs.contrib.simple_history.admin import ConfigHistoryAdmin
from dynamic_configs.models import Config

admin.site.register(Config, ConfigHistoryAdmin)
```

## System checks

The integration checks that simple_history itself is installed. Without it, `manage.py check` (and every `runserver`
and `migrate`) reports the error `dynamic_configs.E101`:

```
?: (dynamic_configs.E101) dynamic_configs.contrib.simple_history is installed, but "simple_history" isn't in INSTALLED_APPS.
	HINT: Add "simple_history" to INSTALLED_APPS.
```

It also reports the error `dynamic_configs.E102` when `SIMPLE_HISTORY_HISTORY_ID_USE_UUID` is set:

```
?: (dynamic_configs.E102) SIMPLE_HISTORY_HISTORY_ID_USE_UUID is set, but the config history's migration creates integer ids, so saving a config would fail.
	HINT: Remove SIMPLE_HISTORY_HISTORY_ID_USE_UUID; the simple-history integration doesn't support it.
```
