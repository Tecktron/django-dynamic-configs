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

An alias that isn't in `CACHES` is reported by the system check `dynamic_configs.E005`, and a value that isn't a
string by `dynamic_configs.E001`; if the server starts anyway, settings are read without a cache and a warning is
logged.

## What's cached

- **One entry per setting:** `dynamic_configs:v1:<name>` holds the tuple `(type_key, stored_text)`, never a
  deserialized value, so your custom classes are never pickled into the cache. `v1` lets a later release change the
  format safely.
  A name long enough to push the cache's full key past 250 characters (Memcached's limit) is keyed by its start and a
  hash of the whole name instead. If your cache's `KEY_PREFIX` is so long that even that key doesn't fit, Memcached
  refuses it: nothing is cached and every read goes to the database.
- **Missing settings** are cached as a marker, so `get(name, default)` for a setting that doesn't exist doesn't query
  the database on every call.
- **Timeout:** `DYNAMIC_CONFIGS["TIMEOUT"]`, default `300` seconds; `None` means no expiry (Django's semantics).

## When the cache is refreshed

- **On save:** the entry is deleted at once, so reads inside the same transaction go to the database. When the
  transaction commits, the row is read again and cached as the database holds it. So a rolled-back save never reaches
  the cache, and a save of some fields only (`save(update_fields=[...])`) never caches an old copy's value.
- **On delete:** the same, writing the missing marker on commit (or the row, if it was created again by then).
- Admin saves, `update`, `delete` and `get_or_create` all go through the model's `save` and `delete`, so they all
  refresh the cache. So does `QuerySet.delete()`, which sends Django's `post_delete` signal for each row.
- `QuerySet.update()`, `bulk_create()` and `bulk_update()` **bypass Django's signals**, so the cache isn't refreshed.
  If you change `Config` rows that way, the old value is served until its entry expires; use `save()` or the API
  instead.
- Data migrations bypass them too: the historical `Config` model a migration gets has no signal receivers. After a
  data migration that changes settings, refresh their cache entries: `get(name, default=None, no_cache=True)` does
  that for one.
- `get_or_create` always reads the database, and so does `get(name, no_cache=True)`. When its transaction commits,
  each reads the row again and caches what the database then holds, as a save does.
- A plain `get` that misses caches what it read when its transaction commits, but only into an empty slot: it never
  replaces an entry. If the slot is empty by then (the entry expired or was evicted) and the setting has changed
  since the read, as can happen in a long transaction, the value it read is cached until the setting is saved or
  refreshed again, or the entry expires.
- With autocommit turned off and no transaction open, there's no commit to wait for, so `get` and `get_or_create`
  leave the cache entry as it is.

If the cache is down while a setting is saved or deleted, the failure is logged as a warning and the save still
succeeds; the old entry, if one is left, expires after `TIMEOUT`. A failed cache read is logged too, and the setting
is read from the database (see [Failure handling and logging](failures.md)).

Memcached's default item limit is 1 MB
([Memcached docs](https://docs.memcached.org/userguide/usecases/#storing-sets-or-lists); servers can raise it with
`-I`). A larger value is read from the database every time, and each read logs a warning.

## Per-process caches

With Django's default `LocMemCache`, each process has its own cache, and an edit only refreshes the cache of the
process that handled it: other processes see the old value until it expires. Under a server with several processes,
use a shared cache (Redis, Memcached), or a short `TIMEOUT`.

## In tests

The package doesn't clear your cache between tests. Use `"CACHE": None` in your test settings, or the test helpers'
overrides, which never touch the cache (see [Testing](testing.md)).
