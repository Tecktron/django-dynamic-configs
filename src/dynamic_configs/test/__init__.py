"""Test helpers: override config values without the database or the cache."""

from __future__ import annotations

import functools
import inspect
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextvars import ContextVar, Token
from typing import Any

from dynamic_configs import _overrides


class override_configs:  # noqa: N801 - lowercase like Django's override_settings, since it's used the same way
    """Override config values in a ``with`` block, or for a decorated function, coroutine function or class.

    ``get`` and ``get_or_create`` return overridden values without touching the cache or the database. Overrides
    layer (an inner block wins), are removed even if the block raises, and are held in a ``ContextVar``, so they
    don't leak between threads or asyncio tasks. One instance can be open in several tasks at once.

    A decorated generator function or async generator function runs under the overrides each time it resumes, while
    its caller's code between items doesn't. Blocks it opens itself hold across its ``yield`` statements, as in any generator.

    Decorating a class applies the overrides to its ``test*`` methods, inherited ones included, to the setup and
    teardown hooks of unittest, Django and pytest (``setUp``, ``asyncSetUp``, ``setUpClass``, ``setUpTestData``,
    ``setup_method``, ``setup_class`` and their teardowns) and to the cleanups ``addCleanup`` registers. Its
    subclasses get the same, decorated or not. A subclass's values win over a decorated base's.

    Example::

        with override_configs(SITE_NAME="Example"):
            assert dynamic_configs.get("SITE_NAME") == "Example"
    """

    # Hooks that run around a class's tests, wrapped like the tests so they see the overrides too, as override_settings
    # applies to a whole class: unittest's and Django's, then pytest's.
    _METHOD_HOOKS = frozenset({"setUp", "tearDown", "asyncSetUp", "asyncTearDown", "setup_method", "teardown_method"})
    _CLASS_HOOKS = frozenset({"setUpClass", "tearDownClass", "setUpTestData", "setup_class", "teardown_class"})
    # A decorated class keeps its own values here. Wrappers merge them along the class's MRO when called, so a subclass
    # wins over its bases, and a method a decorated base already wrapped picks up the subclass's values too.
    _CLASS_VALUES = "_dynamic_configs_overrides"
    _WRAPPED = "_dynamic_configs_wrapped"
    # Each instance's tokens, a stack per instance, held per context: an instance open in two asyncio tasks at once
    # resets each task's token in that task. The mappings are replaced, never changed, since contexts share them.
    _TOKENS: ContextVar[Mapping[override_configs, tuple[Token[Any], ...]]] = ContextVar("dynamic_configs_tokens")

    @classmethod
    def _class_values(cls, test_class: type) -> dict[str, Any]:
        """Return the overrides for ``test_class``: each decorated class's values over its bases'."""
        values: dict[str, Any] = {}
        for klass in reversed(test_class.__mro__):
            values.update(vars(klass).get(cls._CLASS_VALUES, {}))
        return values

    @classmethod
    def _wrap(
        cls, target: Callable[..., Any], values_for: Callable[[tuple[Any, ...]], dict[str, Any]]
    ) -> Callable[..., Any]:
        """Wrap ``target`` to run under the overrides ``values_for`` returns for its arguments."""
        if inspect.isasyncgenfunction(target):
            return cls._wrap_async_generator(target, values_for)
        if inspect.isgeneratorfunction(target):
            return cls._wrap_generator(target, values_for)
        if inspect.iscoroutinefunction(target):

            @functools.wraps(target)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with cls(**values_for(args)):
                    return await target(*args, **kwargs)

            return async_wrapper

        @functools.wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with cls(**values_for(args)):
                return target(*args, **kwargs)

        return wrapper

    @staticmethod
    def _wrap_generator(
        target: Callable[..., Iterator[Any]], values_for: Callable[[tuple[Any, ...]], dict[str, Any]]
    ) -> Callable[..., Iterator[Any]]:
        """Wrap a generator function so its code runs under the overrides each time it resumes.

        The overrides apply step by step, not across ``yield``: the caller's code between items runs without them.
        Blocks the generator opens itself behave as in any generator: they hold across its ``yield``s until they end,
        and its caller sees them meanwhile, as ``@contextmanager`` functions and yield fixtures expect. So the
        decorator's layer is switched in under them for each step, and out again after it. What the caller sends,
        throws or closes is passed on, as ``yield from`` would.
        """

        @functools.wraps(target)
        def generator_wrapper(*args: Any, **kwargs: Any) -> Iterator[Any]:
            generator = target(*args, **kwargs)
            own = _overrides.make_layer(values_for(args))
            above: tuple[_overrides.Layer, ...] = ()

            def step(resume: Callable[..., Any], *sent: Any) -> Any:
                nonlocal above
                _overrides.attach(own, above)
                try:
                    return resume(*sent)
                finally:
                    above = _overrides.detach(own)

            resume, sent = generator.send, None
            while True:
                try:
                    item = step(resume, sent)
                except StopIteration as stop:
                    return stop.value
                try:
                    sent = yield item
                except GeneratorExit:
                    step(generator.close)
                    raise
                except BaseException as error:
                    resume, sent = generator.throw, error
                else:
                    resume = generator.send

        return generator_wrapper

    @staticmethod
    def _wrap_async_generator(
        target: Callable[..., AsyncIterator[Any]], values_for: Callable[[tuple[Any, ...]], dict[str, Any]]
    ) -> Callable[..., AsyncIterator[Any]]:
        """Wrap an async generator function so its code runs under the overrides each time it resumes.

        As ``_wrap_generator``, for ``asend``, ``athrow`` and ``aclose``.
        """

        @functools.wraps(target)
        async def async_generator_wrapper(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            generator = target(*args, **kwargs)
            own = _overrides.make_layer(values_for(args))
            above: tuple[_overrides.Layer, ...] = ()

            async def step(resume: Callable[..., Any], *sent: Any) -> Any:
                nonlocal above
                _overrides.attach(own, above)
                try:
                    return await resume(*sent)
                finally:
                    above = _overrides.detach(own)

            resume, sent = generator.asend, None
            while True:
                try:
                    item = await step(resume, sent)
                except StopAsyncIteration:
                    return
                try:
                    sent = yield item
                except GeneratorExit:
                    await step(generator.aclose)
                    raise
                except BaseException as error:
                    resume, sent = generator.athrow, error
                else:
                    resume = generator.asend

        return async_generator_wrapper

    @classmethod
    def _wrap_hook(
        cls, function: Callable[..., Any], values_for: Callable[[tuple[Any, ...]], dict[str, Any]]
    ) -> Callable[..., Any]:
        """Wrap a setup or teardown hook, keeping its number of positional arguments.

        pytest passes a hook's optional argument (the class, or the test method) only when the hook's code takes it,
        judging by ``__code__.co_argcount``, which a ``*args`` wrapper would hide.
        """
        if inspect.iscoroutinefunction(function):
            # IsolatedAsyncioTestCase's asyncSetUp and asyncTearDown, which take only self: the overrides must hold
            # while they're awaited, not just while they're called.
            return cls._wrap(function, values_for)
        if function.__code__.co_argcount > 1:

            @functools.wraps(function)
            def with_argument(first: Any, second: Any) -> Any:
                with cls(**values_for((first,))):
                    return function(first, second)

            return with_argument

        @functools.wraps(function)
        def without_argument(first: Any) -> Any:
            with cls(**values_for((first,))):
                return function(first)

        return without_argument

    @classmethod
    def _wrap_add_cleanup(cls, add_cleanup: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap ``addCleanup`` so each cleanup it registers runs under the overrides of the test's class.

        Cleanups run after the wrapped ``tearDown`` has returned, and ``IsolatedAsyncioTestCase`` runs them in its own
        copy of the context, so each cleanup carries the overrides itself. ``addAsyncCleanup`` and ``enterContext``
        register through ``addCleanup``.
        """

        @functools.wraps(add_cleanup)
        def wrapper(self: Any, function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
            cleanup = cls._wrap(function, lambda _: cls._class_values(type(self)))
            return add_cleanup(self, cleanup, *args, **kwargs)

        return wrapper

    @classmethod
    def _instance_values(cls, args: tuple[Any, ...]) -> dict[str, Any]:
        """Return the overrides for a method's class, from its ``self``."""
        return cls._class_values(type(args[0]))

    @classmethod
    def _class_hook_values(cls, args: tuple[Any, ...]) -> dict[str, Any]:
        """Return the overrides for a class hook's class, from its ``cls``."""
        return cls._class_values(args[0])

    @classmethod
    def _marked(cls, wrapped: Callable[..., Any]) -> Callable[..., Any]:
        """Mark ``wrapped`` as a class decorator's, so a subclass's decorator doesn't wrap it again."""
        setattr(wrapped, cls._WRAPPED, True)
        return wrapped

    @classmethod
    def _wrap_members(cls, test_class: type) -> None:
        """Wrap the test methods, hooks and ``addCleanup`` of ``test_class``, inherited ones included."""
        for name in dir(test_class):
            member = inspect.getattr_static(test_class, name)
            if isinstance(member, classmethod):
                if name in cls._CLASS_HOOKS and not hasattr(member.__func__, cls._WRAPPED):
                    wrapped = cls._wrap_hook(member.__func__, cls._class_hook_values)
                    setattr(test_class, name, classmethod(cls._marked(wrapped)))
            elif inspect.isfunction(member) and not hasattr(member, cls._WRAPPED):
                if name in cls._METHOD_HOOKS:
                    setattr(test_class, name, cls._marked(cls._wrap_hook(member, cls._instance_values)))
                elif name in cls._CLASS_HOOKS:
                    # pytest also takes setup_class and teardown_class as plain functions, called with the class.
                    setattr(test_class, name, cls._marked(cls._wrap_hook(member, cls._class_hook_values)))
                elif name == "addCleanup":
                    setattr(test_class, name, cls._marked(cls._wrap_add_cleanup(member)))
                elif name.startswith("test"):
                    setattr(test_class, name, cls._marked(cls._wrap(member, cls._instance_values)))

    @classmethod
    def _wrap_subclasses(cls, test_class: type) -> None:
        """Have each subclass of ``test_class`` wrapped as it's created, so its own tests and hooks get the overrides.

        Django's ``override_settings`` stores its values on the class, and ``SimpleTestCase.setUpClass``, which every
        subclass inherits, applies them. This decorator also takes classes with no common base, such as plain pytest
        classes, so ``__init_subclass__`` is the hook every subclass passes through.
        """
        if hasattr(getattr(test_class.__init_subclass__, "__func__", None), cls._WRAPPED):
            return  # A decorated base, or another decorator on this class, already did.
        own = vars(test_class).get("__init_subclass__")

        def init_subclass(subclass: type, **kwargs: Any) -> None:
            if own is None:
                super(test_class, subclass).__init_subclass__(**kwargs)
            else:
                own.__get__(None, subclass)(**kwargs)
            cls._wrap_members(subclass)

        test_class.__init_subclass__ = classmethod(cls._marked(init_subclass))

    def __init__(self, **values: Any) -> None:
        """Store the values to override, keyed by config name."""
        self.values = values

    def __enter__(self) -> override_configs:
        """Apply the overrides on top of any already active."""
        tokens = self._TOKENS.get({})
        token = _overrides.push(self.values)
        self._TOKENS.set({**tokens, self: (*tokens.get(self, ()), token)})
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Remove these overrides, restoring the ones active before."""
        tokens = dict(self._TOKENS.get({}))
        *rest, token = tokens.pop(self)
        if rest:
            tokens[self] = tuple(rest)
        self._TOKENS.set(tokens)
        _overrides.pop(token)

    def __call__(self, target: Any) -> Any:
        """Decorate a function, coroutine function, (async) generator function or class with these overrides."""
        if isinstance(target, type):
            return self._decorate_class(target)
        values = self.values
        return self._wrap(target, lambda args: values)

    def _decorate_class(self, test_class: type) -> type:
        """Record these values on ``test_class``, wrap its tests and hooks, and have its subclasses' wrapped too."""
        # With decorators stacked on one class, the inner one (applied first) wins, as on functions.
        setattr(test_class, self._CLASS_VALUES, {**self.values, **vars(test_class).get(self._CLASS_VALUES, {})})
        self._wrap_members(test_class)
        self._wrap_subclasses(test_class)
        return test_class
