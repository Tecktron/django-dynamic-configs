# Reading and writing settings

The API is four functions and their async variants, all importable from the package:

```python
from dynamic_configs import get, get_or_create, update, delete

get(name, default=<missing>, *, no_cache=False)  # -> value
get_or_create(name, type, value, *, description="", allow_null=False)  # -> (value, created)
update(name, new_value, *, allow_null=None)  # -> None
delete(name)  # -> bool
aget(...), aget_or_create(...), aupdate(...), adelete(...)  # async, same arguments
```

The functions are loaded on first use, so importing `dynamic_configs` doesn't import its models, and is safe in
modules Django loads early, such as an app's `apps.py`.

## Names

A setting's name must match `^[A-Z][A-Z0-9_]*$`: a capital letter, then capital letters, digits and underscores
(`SITE_NAME`, `MAX_UPLOAD_MB`, `FEATURE_2FA`). A name can't be changed once the setting exists.

## `get`

```python
get(name, default=<missing>, *, no_cache=False)
```

Returns the setting's value, as its type's Python type, or `None` for an empty setting that allows it
(`allow_null`).

- When the setting doesn't exist and you passed no default, it raises `ConfigDoesNotExist`. With a default, it
  returns the default.
- **If you pass a default, `get` never raises**: a database error or a stored value that can't be read also returns
  the default, and is logged (see [Failure handling and logging](failures.md)).
- A name that doesn't match the name pattern can never be saved, so `get` treats it as missing without touching the
  cache or the database.
- `no_cache=True` skips the cache read and reads the database, then refreshes the cache entry with what it read.
- Overrides from the test helpers come first (see [Testing](testing.md)).

## `get_or_create`

```python
get_or_create(name, type, value, *, description="", allow_null=False)
```

Returns `(value, created)`.

- It always reads the database, then refreshes the cache, so code that declares its settings this way sees what an
  admin has changed.
- When the setting exists, it returns the stored value and `created=False`; `type`, `value`, `description` and
  `allow_null` are not used, except that a setting stored with a different type raises `ConfigTypeError`.
- When it doesn't exist, it checks the name, the type key and the value, creates the setting, and returns
  `(value, True)`. The value comes back as `get` will return it (a naive datetime comes back in UTC, for example).
- Two processes creating the same setting at once is safe: Django's `get_or_create` handles it.
- `value=None` needs `allow_null=True`.

## `update`

```python
update(name, new_value, *, allow_null=None)
```

Changes an existing setting, inside a transaction that locks its row (`select_for_update`).

- `allow_null=None` keeps the setting's flag; `True` or `False` changes it in the same save.
- `new_value=None` is accepted only when the resulting flag is `True`.
- It raises `ConfigDoesNotExist` if the setting is missing, `ConfigTypeError` if the value fails the type check, and
  `ConfigValueError` if the type's serializer rejects the value or the setting's type is no longer registered.

## `delete`

```python
delete(name)
```

Returns `True` if it deleted the setting, `False` if it didn't exist. It never raises for a missing setting.

## Async variants

`aget`, `aget_or_create`, `aupdate` and `adelete` take the same arguments and return the same values. They run the
sync functions with `asgiref.sync.sync_to_async`, so they behave exactly alike.

## Saving without the API

Admin saves and the API go through the model's `save` and `delete`, which keep the cache in step. If you change
`Config` rows yourself, use the model's `save()` and `delete()` (or `QuerySet.delete()`) too:
`QuerySet.update()`, `bulk_create()` and `bulk_update()` don't send Django's signals, so the cache keeps the old value
until it expires (see [Caching](caching.md)).

## Exceptions

`ConfigDoesNotExist` is defined in `dynamic_configs.models`, since it needs the model, and the others in
`dynamic_configs.exceptions`. All are importable from `dynamic_configs`:

```python
from dynamic_configs import ConfigDoesNotExist, ConfigError, ConfigTypeError, ConfigValueError
```

| Exception            | Bases                                | Raised when                                                 |
|----------------------|--------------------------------------|-------------------------------------------------------------|
| `ConfigError`        | `Exception`                          | base class                                                  |
| `ConfigDoesNotExist` | `ConfigError`, `Config.DoesNotExist` | the setting doesn't exist (so `except ObjectDoesNotExist` works) |
| `ConfigTypeError`    | `ConfigError`, `TypeError`           | a value fails the type check; an unknown type key is passed; `get_or_create` finds a different type |
| `ConfigValueError`   | `ConfigError`, `ValueError`          | an invalid name; the serializer rejects a value; a set type is given duplicates; a stored value can't be deserialized; a stored type is no longer registered |

Because each also subclasses a built-in exception, code that already catches `TypeError`, `ValueError` or Django's
`ObjectDoesNotExist` keeps working.
