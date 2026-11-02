"""Test helpers: override config values without the database or the cache."""

from __future__ import annotations

import functools
import inspect
from contextvars import Token
from typing import Any

from dynamic_configs import _overrides


class override_configs:  # noqa: N801 - lowercase like Django's override_settings, since it's used the same way
    """Override config values in a ``with`` block, or for a decorated function, coroutine function or class.

    ``get`` and ``get_or_create`` return overridden values without touching the cache or the database. Overrides
    layer (an inner block wins), are removed even if the block raises, and are held in a ``ContextVar``, so they
    don't leak between threads or asyncio tasks. Decorating a class wraps each of its ``test*`` methods.

    Example::

        with override_configs(SITE_NAME="Example"):
            assert dynamic_configs.get("SITE_NAME") == "Example"
    """

    def __init__(self, **values: Any) -> None:
        """Store the values to override, keyed by config name."""
        self.values = values
        self._tokens: list[Token[Any]] = []

    def __enter__(self) -> override_configs:
        """Apply the overrides on top of any already active."""
        self._tokens.append(_overrides.push(self.values))
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Remove these overrides, restoring the ones active before."""
        _overrides.pop(self._tokens.pop())

    def __call__(self, target: Any) -> Any:
        """Decorate a function, coroutine function or class with these overrides."""
        if isinstance(target, type):
            return self._decorate_class(target)
        values = self.values
        if inspect.iscoroutinefunction(target):

            @functools.wraps(target)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with override_configs(**values):
                    return await target(*args, **kwargs)

            return async_wrapper

        @functools.wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with override_configs(**values):
                return target(*args, **kwargs)

        return wrapper

    def _decorate_class(self, cls: type) -> type:
        """Wrap each callable ``test*`` attribute of ``cls``."""
        for attribute, member in list(vars(cls).items()):
            if attribute.startswith("test") and callable(member):
                setattr(cls, attribute, self(member))
        return cls
