# Quick start

This walks through one setting, `PAGE_SIZE`, from code to the admin and back. It assumes the package is installed
and migrated (see [Installation](installation.md)).

## Declare a setting

`get_or_create` creates the setting the first time it runs, and returns what's stored every time after:

```python
import dynamic_configs

page_size, created = dynamic_configs.get_or_create(
    "PAGE_SIZE",
    "int",
    20,
    description="How many items a list page shows.",
)
```

Names are UPPER_SNAKE_CASE: a capital letter, then capital letters, digits and underscores. The type is a type key,
such as `"int"`, `"str"`, `"hours"` or `"list:str"` (see [Types](types.md)), and it can't change once the setting
exists. The value must be of that type: `get_or_create("PAGE_SIZE", "int", "20")` raises `ConfigTypeError`.

`get_or_create` always reads the database, so once an admin has changed the setting, it returns the admin's value,
not the one in your code. Call it where a database query is fine, such as a management command your deploy runs.

## Read it

```python
page_size = dynamic_configs.get("PAGE_SIZE", 20)
```

`get` returns the typed value: an `int` here, a `timedelta` for an `hours` setting, a `list` for a `list:str`
setting. Reads go through the cache when one is configured (see [Caching](caching.md)).

Pass a default wherever a missing or unreadable setting shouldn't break the page: with a default, `get` never raises
(see [Failure handling and logging](failures.md)). Without one, a missing setting raises `ConfigDoesNotExist`.

## Change it from code

```python
dynamic_configs.update("PAGE_SIZE", 50)
```

`update` changes an existing setting; the cache is refreshed when the change commits. `delete("PAGE_SIZE")` removes
it.

## Edit it in the admin

Open the Django admin and choose **Configs**. The list shows each setting's name, type, value and description.

- **To change a setting**, open it. Its value uses its type's own input: a number box for `int`, a checkbox for
  `bool`, the date picker for `date`, the list editor for list and set types. The name and type can't be changed.
- **To add a setting**, click **Add config**, choose its type and click **Save**; then enter the name, the value and
  an optional description, and save again. The value is checked by its type before it's saved.

Code reading the setting sees the admin's change as soon as the save commits, in the process that handled it, and in
other processes too when the cache is shared (see [Caching](caching.md#per-process-caches)).

## Async code

Every function has an async variant with the same arguments: `aget`, `aget_or_create`, `aupdate` and `adelete`.

```python
page_size = await dynamic_configs.aget("PAGE_SIZE", 20)
```
