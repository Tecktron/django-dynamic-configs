# django-dynamic-configs

Typed runtime settings for Django that admins can **add** and edit in the Django admin, read from code through a
small, cached API. It replaces the settings model each project would otherwise write for itself.

```python
import dynamic_configs

dynamic_configs.get_or_create("PAGE_SIZE", "int", 20, description="Items per page.")
page_size = dynamic_configs.get("PAGE_SIZE", 20)
```

## What you get

- Admins can add, edit and delete settings. Each has a unique name, a type, a value and an optional description.
- A small API: `get`, `get_or_create`, `update` and `delete`, plus async variants.
- Typed values: strings, numbers, booleans, dates, datetimes, JSON and durations, a list and a set variant of every
  type except JSON, and custom types you declare in Django settings.
- Nothing an admin enters is ever imported, evaluated or executed. Types come only from code.
- Cached reads when a cache is configured. A caller that passes a default is never broken by an outage.
- Works under admin skins (jazzmin, grappelli, unfold), because it uses the stock admin pages.
- An optional integration with django-simple-history. It isn't required.
- Test helpers that need neither the database nor the cache.
- Supports Django 5.2 and later, on every Python each supported Django release supports.

```{toctree}
:maxdepth: 2

installation
quickstart
api
types
money
caching
failures
admin
simple-history
testing
reference
changelog
development
```
