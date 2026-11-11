# Caching

Reads are cached when a cache is configured, so `get` usually doesn't query the database.

## Turning it on and off

Caching is on when `DYNAMIC_CONFIGS["CACHE"]` names a cache alias (the default is `"default"`) whose backend isn't
`DummyCache`. Set it to `None` to turn caching off:

```python
DYNAMIC_CONFIGS = {
    "CACHE": "configs",   # an alias in CACHES
    "TIMEOUT": 300,       # seconds; None means no expiry
}
```

An alias that isn't in `CACHES` is reported by the system check `dynamic_configs.E005`; if the server starts anyway,
settings are read without a cache and a warning is logged.

## What's cached

- **One entry per setting:** `dynamic_configs:v1:<name>` holds the tuple `(type_key, stored_text)`, never a
  deserialized value, so your custom classes are never pickled into the cache. `v1` lets a later release change the
  format safely.
- **Missing settings** are cached as a marker, so `get(name, default)` for a setting that doesn't exist doesn't query
  the database on every call.
- **Timeout:** `DYNAMIC_CONFIGS["TIMEOUT"]`, default `300` seconds; `None` means no expiry (Django's semantics).

## When the cache is refreshed

- **On save:** the entry is deleted at once, so reads inside the same transaction go to the database, then replaced
  with the new value when the transaction commits, so a rolled-back save never reaches the cache.
- **On delete:** the same, writing the missing marker on commit.
- Admin saves, `update`, `delete` and `get_or_create` all go through the model's `save` and `delete`, so they all
  refresh the cache. So does `QuerySet.delete()`, which sends Django's `post_delete` signal for each row.
- `QuerySet.update()`, `bulk_create()` and `bulk_update()` **bypass Django's signals**, so the cache isn't refreshed.
  If you change `Config` rows that way, the old value is served until its entry expires; use `save()` or the API
  instead.
- `get_or_create` always reads the database and refreshes the entry with what it read, and so does
  `get(name, no_cache=True)`.

If the cache is down while a setting is saved or deleted, the failure is logged as a warning and the save still
succeeds; the old entry, if one is left, expires after `TIMEOUT`. A failed cache read is logged too, and the setting
is read from the database (see [Failure handling and logging](failures.md)).

## Per-process caches

With Django's default `LocMemCache`, each process has its own cache, and an edit only refreshes the cache of the
process that handled it: other processes see the old value until it expires. Under a server with several processes,
use a shared cache (Redis, Memcached), or a short `TIMEOUT`.

## In tests

The package doesn't clear your cache between tests. Use `"CACHE": None` in your test settings, or the test helpers'
overrides, which never touch the cache (see [Testing](testing.md)).
