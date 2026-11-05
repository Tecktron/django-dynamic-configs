"""Test helpers: override config values without the database or the cache."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from contextvars import Token
from typing import Any

from dynamic_configs import _overrides

# Hooks that run around a class's tests, wrapped like the tests so they see the overrides too, as override_settings
# applies to a whole class: unittest's and Django's, then pytest's.
_METHOD_HOOKS = frozenset({"setUp", "tearDown", "setup_method", "teardown_method"})
_CLASS_HOOKS = frozenset({"setUpClass", "tearDownClass", "setUpTestData", "setup_class", "teardown_class"})
# A decorated class keeps its own values here. Wrappers merge them along the class's MRO when called, so a subclass
# wins over its bases, and a method a decorated base already wrapped picks up the subclass's values too.
_CLASS_VALUES = "_dynamic_configs_overrides"
_WRAPPED = "_dynamic_configs_wrapped"


def _class_values(cls: type) -> dict[str, Any]:
    """Return the overrides for ``cls``: each decorated class's values over its bases'."""
    values: dict[str, Any] = {}
    for klass in reversed(cls.__mro__):
        values.update(vars(klass).get(_CLASS_VALUES, {}))
    return values


def _wrap(target: Callable[..., Any], values_for: Callable[[tuple[Any, ...]], dict[str, Any]]) -> Callable[..., Any]:
    """Wrap ``target`` to run under the overrides ``values_for`` returns for its arguments."""
    if inspect.iscoroutinefunction(target):

        @functools.wraps(target)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with override_configs(**values_for(args)):
                return await target(*args, **kwargs)

        return async_wrapper

    @functools.wraps(target)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with override_configs(**values_for(args)):
            return target(*args, **kwargs)

    return wrapper


def _wrap_hook(
    function: Callable[..., Any], values_for: Callable[[tuple[Any, ...]], dict[str, Any]]
) -> Callable[..., Any]:
    """Wrap a setup or teardown hook, keeping its number of positional arguments.

    pytest passes a hook's optional argument (the class, or the test method) only when the hook's code takes it,
    judging by ``__code__.co_argcount``, which a ``*args`` wrapper would hide.
    """
    if function.__code__.co_argcount > 1:

        @functools.wraps(function)
        def with_argument(first: Any, second: Any) -> Any:
            with override_configs(**values_for((first,))):
                return function(first, second)

        return with_argument

    @functools.wraps(function)
    def without_argument(first: Any) -> Any:
        with override_configs(**values_for((first,))):
            return function(first)

    return without_argument


def _instance_values(args: tuple[Any, ...]) -> dict[str, Any]:
    """Return the overrides for a method's class, from its ``self``."""
    return _class_values(type(args[0]))


def _class_hook_values(args: tuple[Any, ...]) -> dict[str, Any]:
    """Return the overrides for a class hook's class, from its ``cls``."""
    return _class_values(args[0])


def _marked(wrapped: Callable[..., Any]) -> Callable[..., Any]:
    """Mark ``wrapped`` as a class decorator's, so a subclass's decorator doesn't wrap it again."""
    setattr(wrapped, _WRAPPED, True)
    return wrapped


class override_configs:  # noqa: N801 - lowercase like Django's override_settings, since it's used the same way
    """Override config values in a ``with`` block, or for a decorated function, coroutine function or class.

    ``get`` and ``get_or_create`` return overridden values without touching the cache or the database. Overrides
    layer (an inner block wins), are removed even if the block raises, and are held in a ``ContextVar``, so they
    don't leak between threads or asyncio tasks.

    Decorating a class applies the overrides to its ``test*`` methods, inherited ones included, and to the setup and
    teardown hooks of unittest, Django and pytest (``setUp``, ``setUpClass``, ``setUpTestData``, ``setup_method``,
    ``setup_class`` and their teardowns). A subclass's values win over a decorated base's.

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
        return _wrap(target, lambda args: values)

    def _decorate_class(self, cls: type) -> type:
        """Record these values on ``cls`` and wrap its test methods and hooks, inherited ones included."""
        # With decorators stacked on one class, the inner one (applied first) wins, as on functions.
        setattr(cls, _CLASS_VALUES, {**self.values, **vars(cls).get(_CLASS_VALUES, {})})
        for name in dir(cls):
            member = inspect.getattr_static(cls, name)
            if isinstance(member, classmethod):
                if name in _CLASS_HOOKS and not hasattr(member.__func__, _WRAPPED):
                    setattr(cls, name, classmethod(_marked(_wrap_hook(member.__func__, _class_hook_values))))
            elif inspect.isfunction(member) and not hasattr(member, _WRAPPED):
                if name in _METHOD_HOOKS:
                    setattr(cls, name, _marked(_wrap_hook(member, _instance_values)))
                elif name in _CLASS_HOOKS:
                    # pytest also takes setup_class and teardown_class as plain functions, called with the class.
                    setattr(cls, name, _marked(_wrap_hook(member, _class_hook_values)))
                elif name.startswith("test"):
                    setattr(cls, name, _marked(_wrap(member, _instance_values)))
        return cls
