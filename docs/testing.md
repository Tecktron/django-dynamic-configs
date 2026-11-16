# Testing

The test helpers set the value code reads for a setting without the database or the cache, so tests of code that
reads settings don't need either.

## `override_configs`

`dynamic_configs.test.override_configs(**values)` is a context manager and a decorator, used like Django's
`override_settings`:

```python
import dynamic_configs
from dynamic_configs.test import override_configs


def test_page_size():
    with override_configs(PAGE_SIZE=5):
        assert dynamic_configs.get("PAGE_SIZE") == 5


@override_configs(PAGE_SIZE=5, SITE_NAME="Example")
def test_listing():
    ...
```

- `get` returns an overridden value, and `get_or_create` returns it as `(value, False)`, without touching the cache or
  the database. The setting doesn't have to exist, and the value isn't type-checked.
- `update` and `delete` aren't overridden: they change the database as usual.
- Overrides layer, so an inner block wins, and they're removed when the block ends, even if it raises.
- They don't leak between threads or asyncio tasks, and they apply in the async variants (`aget`, `aget_or_create`).
  One instance can be open in several tasks at once; each task's block ends on its own.
- It decorates functions, coroutine functions, generator functions and async generator functions. A decorated
  generator runs under the overrides each time it resumes, so they hold while it's iterated, not only while it's
  created. The code that iterates it doesn't see them between items.

### On a class

On a class, like `override_settings`, it covers the whole class: its `test*` methods, inherited ones included, the
setup and teardown hooks of unittest, Django and pytest (`setUp`, `asyncSetUp`, `setUpClass`, `setUpTestData`,
`setup_method`, `setup_class` and their teardowns), and the cleanups registered with `addCleanup`, `addAsyncCleanup`
or `enterContext`.

```python
from django.test import TestCase

from dynamic_configs.test import override_configs


@override_configs(PAGE_SIZE=5)
class ListingTests(TestCase):
    def test_first_page(self):
        ...
```

Subclasses are covered too, decorated or not: a subclass's own `test*` methods and hooks see the base's overrides. A
subclass's own decorator layers on top, so its values win over a decorated base's. With two decorators stacked on one
class, the inner one wins, as on functions.

## The pytest plugin

The package registers a pytest plugin when it's installed, with nothing to configure. Its `config_overrides` fixture
applies overrides for the rest of the test, and clears them at teardown:

```python
import dynamic_configs


def test_page_size(config_overrides):
    config_overrides.set(PAGE_SIZE=5)
    assert dynamic_configs.get("PAGE_SIZE") == 5
```

Each `.set()` adds to the overrides already set. A `.set()` inside a `with override_configs(...)` block, or in a test
of a decorated class, still holds after the block ends, for the rest of the test. The latest wins: `.set()` beats a
block or class decorator that names the same setting and was applied before it, and a block opened after `.set()` beats
it until the block ends:

```python
import dynamic_configs
from dynamic_configs.test import override_configs


def test_precedence(config_overrides):
    with override_configs(PAGE_SIZE=5):
        config_overrides.set(PAGE_SIZE=10)
        assert dynamic_configs.get("PAGE_SIZE") == 10
    assert dynamic_configs.get("PAGE_SIZE") == 10
    with override_configs(PAGE_SIZE=20):
        assert dynamic_configs.get("PAGE_SIZE") == 20
    assert dynamic_configs.get("PAGE_SIZE") == 10
```

The fixture isn't named `dynamic_configs`, which would hide the module inside tests that also call
`dynamic_configs.get`. The plugin imports nothing from Django when pytest starts, so it works in projects whose Django
settings load later.

## The cache in tests

Neither helper clears your project's cache between tests, and a setting saved in one test can be served from the
cache in the next. Use `"CACHE": None` in your test settings, or overrides, which never touch the cache:

```python
# test settings
DYNAMIC_CONFIGS = {"CACHE": None}
```

Django's `TestCase` never commits, so the cache writes that wait for a commit don't run there. A test that needs them
uses `captureOnCommitCallbacks(execute=True)`:

```python
with self.captureOnCommitCallbacks(execute=True):
    dynamic_configs.update("PAGE_SIZE", 50)
```
