# Failure handling and logging

## Failure handling

One rule: **if you pass a default, `get` never raises.**

| Situation                                     | `get` with a default        | `get` without a default      |
|-----------------------------------------------|-----------------------------|------------------------------|
| Setting doesn't exist                         | returns the default         | raises `ConfigDoesNotExist`  |
| Cache error (read or write)                   | logged as a warning; falls through to the database | same                |
| Database error (`DatabaseError`)              | logged as a warning; returns the default | the error propagates  |
| Stored value unreadable, or its type isn't registered | logged as an error; returns the default | raises `ConfigValueError` |
| `allow_null` and empty                        | returns `None`              | returns `None`               |

So pass a default wherever a broken setting, a database outage or a cache outage shouldn't break the page:

```python
page_size = dynamic_configs.get("PAGE_SIZE", 20)
```

A stored value is unreadable when its type's serializer rejects it (a row edited by hand, say, or a custom type whose
rules got stricter). Its type isn't registered when the type was removed from `TYPES`, or its entry there is broken:
a broken entry doesn't stop other settings being read, but it's logged as an error and skipped, and settings of that
type read as unregistered until it's fixed (`manage.py check` says what's wrong). In the admin, such a setting shows
its stored text read-only (see [Admin and skins](admin.md#unregistered-types)).

If a logging handler of yours itself calls `get` (to decide what to redact, say), it can't recurse while the
database or cache is down: a `get` that runs inside the package's own logging doesn't log.

## Logging

Each module logs to its own logger under `dynamic_configs` (`dynamic_configs.api`, `dynamic_configs.cache`,
`dynamic_configs.types.registry`, ...), so you can tune them together or separately:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "dynamic_configs": {"handlers": ["console"], "level": "INFO"},
    },
}
```

| Level     | Used for                                                                                       |
|-----------|------------------------------------------------------------------------------------------------|
| `DEBUG`   | cache hits, misses and refreshes; database reads; the registry being built or rebuilt          |
| `INFO`    | writes made through the API: a setting created by `get_or_create`, changed by `update`, deleted by `delete` |
| `WARNING` | a cache error (falling through to the database); a database error answered with the default    |
| `ERROR`   | a stored value that can't be deserialized; a stored type that is no longer registered          |

- **Setting values are never logged, at any level**, because settings may hold secrets (API keys, tokens). Messages
  carry the setting's name and type key only.
- Messages name the setting and say what happens next (for example "Cache read failed for config 'PAGE_SIZE';
  reading from the database"). Cache and database errors are logged with their traceback.
- Every record about a setting carries `config_name` (and `config_type` where known) as extra attributes, so
  structured log handlers can filter on them.
- Changes made in the admin aren't logged by the package: Django's admin keeps its own log of them.
- Problems in the configuration are reported by Django's system checks at startup (see
  [System checks](installation.md#system-checks)). Since a server may not run the checks, two are also logged when
  they're met at run time: a broken `TYPES` entry, skipped, as an error, and a `CACHE` alias that isn't in `CACHES`
  as a warning.
