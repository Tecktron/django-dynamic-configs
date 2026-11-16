import asyncio
import threading
import unittest
from contextlib import contextmanager

import pytest
from django.test import TestCase

import dynamic_configs
from dynamic_configs import _overrides
from dynamic_configs.test import override_configs


def test_as_a_context_manager():
    with override_configs(SITE_NAME="Example") as overrides:
        assert dynamic_configs.get("SITE_NAME") == "Example"
        assert overrides.values == {"SITE_NAME": "Example"}
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_nested_overrides_layer_and_unwind():
    with override_configs(SITE_NAME="Outer", MAX_RETRIES=3):
        with override_configs(SITE_NAME="Inner"):
            assert dynamic_configs.get("SITE_NAME") == "Inner"
            assert dynamic_configs.get("MAX_RETRIES") == 3
        assert dynamic_configs.get("SITE_NAME") == "Outer"


def test_overrides_are_removed_when_the_block_raises():
    with pytest.raises(RuntimeError), override_configs(SITE_NAME="Example"):
        raise RuntimeError("boom")
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_get_or_create_returns_overrides_too():
    with override_configs(MAX_RETRIES=9):
        assert dynamic_configs.get_or_create("MAX_RETRIES", "int", 3) == (9, False)


@override_configs(SITE_NAME="Decorated")
def test_as_a_function_decorator():
    assert dynamic_configs.get("SITE_NAME") == "Decorated"


def test_decorated_coroutine_functions_keep_the_overrides_while_awaited():
    @override_configs(SITE_NAME="Async")
    async def read():
        await asyncio.sleep(0)
        return dynamic_configs.get("SITE_NAME")

    assert asyncio.run(read()) == "Async"
    assert _overrides.lookup("SITE_NAME") == (False, None)


@override_configs(SITE_NAME="Class")
class TestAsAClassDecorator:
    test_data = "not a method, so left alone"

    def test_methods_see_the_overrides(self):
        assert dynamic_configs.get("SITE_NAME") == "Class"

    def helper(self):
        return _overrides.lookup("SITE_NAME")

    def test_only_test_methods_are_wrapped(self):
        # functools.wraps sets __wrapped__ on the wrappers, so it marks exactly what was decorated.
        assert hasattr(TestAsAClassDecorator.test_methods_see_the_overrides, "__wrapped__")
        assert not hasattr(TestAsAClassDecorator.helper, "__wrapped__")
        assert self.test_data == "not a method, so left alone"


class _Base:
    def test_inherited_methods_see_the_overrides(self):
        assert _overrides.lookup("SITE_NAME") == (True, "Subclass")


@override_configs(SITE_NAME="Subclass")
class TestInheritedTestMethods(_Base):
    """Review: only methods defined on the decorated class itself were wrapped."""


@override_configs(SITE_NAME="Base", MAX_RETRIES=1)
class _DecoratedBase:
    def test_a_subclass_wins_over_its_decorated_base(self):
        assert _overrides.lookup("SITE_NAME") == (True, "Subclass")
        assert _overrides.lookup("MAX_RETRIES") == (True, 1)


@override_configs(SITE_NAME="Subclass")
class TestSubclassOfADecoratedBase(_DecoratedBase):
    pass


@override_configs(SITE_NAME="Class")
class TestPytestSetupHooks:
    @classmethod
    def setup_class(cls):
        cls.seen_in_setup_class = _overrides.lookup("SITE_NAME")

    def setup_method(self, method):
        # Taking the optional argument: pytest passes it only if the (wrapped) hook's code accepts it.
        self.seen_in_setup_method = (method.__name__, _overrides.lookup("SITE_NAME"))

    def test_setup_hooks_see_the_overrides(self):
        assert self.seen_in_setup_class == (True, "Class")
        assert self.seen_in_setup_method == ("test_setup_hooks_see_the_overrides", (True, "Class"))


@override_configs(SITE_NAME="Class")
class TestPlainSetupClass:
    # pytest also takes setup_class as a plain function, which it calls with the class.
    def setup_class(cls):  # noqa: N805
        cls.seen_in_setup_class = _overrides.lookup("SITE_NAME")

    def test_a_plain_setup_class_sees_the_overrides(self):
        assert self.seen_in_setup_class == (True, "Class")


@override_configs(SITE_NAME="Class")
class TestDjangoTestCaseHooks(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seen_in_set_up_test_data = _overrides.lookup("SITE_NAME")

    def setUp(self):
        self.seen_in_set_up = _overrides.lookup("SITE_NAME")

    def test_set_up_hooks_see_the_overrides(self):
        assert self.seen_in_set_up_test_data == (True, "Class")
        assert self.seen_in_set_up == (True, "Class")


def test_async_test_methods_of_a_decorated_class_see_the_overrides():
    @override_configs(SITE_NAME="Async class")
    class Tests:
        async def test_read(self):
            await asyncio.sleep(0)
            return _overrides.lookup("SITE_NAME")

    assert asyncio.run(Tests().test_read()) == (True, "Async class")


@override_configs(SITE_NAME="Outer", MAX_RETRIES=1)
@override_configs(SITE_NAME="Inner")
class TestStackedClassDecorators:
    def test_the_inner_decorator_wins_as_on_functions(self):
        assert _overrides.lookup("SITE_NAME") == (True, "Inner")
        assert _overrides.lookup("MAX_RETRIES") == (True, 1)


def test_overrides_do_not_leak_between_asyncio_tasks():
    # Review focus: each task starts from a copy of the context, so one task's overrides stay its own.
    async def scenario():
        ready = asyncio.Event()
        seen = []

        async def setter():
            with override_configs(SITE_NAME="Task A"):
                ready.set()
                await asyncio.sleep(0)

        async def reader():
            await ready.wait()
            seen.append(_overrides.lookup("SITE_NAME"))

        await asyncio.gather(setter(), reader())
        return seen

    assert asyncio.run(scenario()) == [(False, None)]


def test_an_undecorated_subclass_keeps_the_overrides():
    # F9: a subclass's own tests and setup hooks ran without the decorated base's overrides.
    seen = {}

    @override_configs(SITE_NAME="Base")
    class Base(unittest.TestCase):
        pass

    class Child(Base):
        def setUp(self):
            seen["setUp"] = _overrides.lookup("SITE_NAME")

        def test_x(self):
            seen["test_x"] = _overrides.lookup("SITE_NAME")

    result = unittest.TestResult()
    Child("test_x").run(result)
    assert result.wasSuccessful()

    @override_configs(SITE_NAME="Base", MAX_RETRIES=1)
    class PlainBase:
        pass

    class PlainChild(PlainBase):
        def setup_method(self, method):
            seen["setup_method"] = _overrides.lookup("SITE_NAME")

        def test_x(self):
            seen["plain test_x"] = _overrides.lookup("SITE_NAME")

    child = PlainChild()
    child.setup_method(PlainChild.test_x)
    child.test_x()

    # A subclass with its own decorator layers on top of its base's, as with override_settings.
    @override_configs(SITE_NAME="Grandchild")
    class Grandchild(PlainChild):
        def test_y(self):
            seen["grandchild test_y"] = (_overrides.lookup("SITE_NAME"), _overrides.lookup("MAX_RETRIES"))

    Grandchild().test_y()
    assert seen == {
        "setUp": (True, "Base"),
        "test_x": (True, "Base"),
        "setup_method": (True, "Base"),
        "plain test_x": (True, "Base"),
        "grandchild test_y": ((True, "Grandchild"), (True, 1)),
    }
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_a_class_with_its_own_init_subclass_keeps_it():
    calls = []

    @override_configs(SITE_NAME="Base")
    class Base:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            calls.append(cls.__name__)

    class Child(Base):
        def test_x(self):
            return _overrides.lookup("SITE_NAME")

    assert calls == ["Child"]
    assert Child().test_x() == (True, "Base")


def test_one_instance_entered_in_two_tasks_at_once():
    # F12: the instance kept its tokens in one shared list, so one task's exit reset the other task's token.
    shared = override_configs(SITE_NAME="Shared")

    async def task(own_value):
        with override_configs(SITE_NAME=own_value):
            with shared:
                await asyncio.sleep(0)
                inside = _overrides.lookup("SITE_NAME")
                await asyncio.sleep(0)
            return inside, _overrides.lookup("SITE_NAME")

    async def scenario():
        return await asyncio.gather(task("A"), task("B"))

    assert asyncio.run(scenario()) == [((True, "Shared"), (True, "A")), ((True, "Shared"), (True, "B"))]


def test_one_instance_can_be_entered_again_inside_itself():
    overrides = override_configs(SITE_NAME="Example")
    with overrides:
        with override_configs(SITE_NAME="Between"), overrides:
            assert _overrides.lookup("SITE_NAME") == (True, "Example")
        assert _overrides.lookup("SITE_NAME") == (True, "Example")
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_decorated_generators_async_generators_cleanups_and_asyncsetup_see_overrides():
    # F14: these ran after the decorated call had returned, or outside the wrapped methods.
    @override_configs(SITE_NAME="Generator")
    def generator():
        yield _overrides.lookup("SITE_NAME")
        yield _overrides.lookup("SITE_NAME")

    items = generator()
    assert next(items) == (True, "Generator")
    # Only the generator's own code runs under the overrides, not its caller's between items.
    assert _overrides.lookup("SITE_NAME") == (False, None)
    assert list(items) == [(True, "Generator")]

    @override_configs(SITE_NAME="Async generator")
    async def async_generator():
        await asyncio.sleep(0)
        yield _overrides.lookup("SITE_NAME")

    async def collect():
        return [item async for item in async_generator()], _overrides.lookup("SITE_NAME")

    assert asyncio.run(collect()) == ([(True, "Async generator")], (False, None))

    seen = {}

    @override_configs(SITE_NAME="Cleanups")
    class Tests(unittest.TestCase):
        def setUp(self):
            self.addCleanup(lambda: seen.setdefault("cleanup", _overrides.lookup("SITE_NAME")))

        def test_x(self):
            pass

    @override_configs(SITE_NAME="Async case")
    class AsyncTests(unittest.IsolatedAsyncioTestCase):
        async def asyncSetUp(self):
            seen["asyncSetUp"] = _overrides.lookup("SITE_NAME")

        async def asyncTearDown(self):
            seen["asyncTearDown"] = _overrides.lookup("SITE_NAME")

        async def test_x(self):
            async def cleanup():
                seen["async cleanup"] = _overrides.lookup("SITE_NAME")

            self.addAsyncCleanup(cleanup)

    result = unittest.TestResult()
    Tests("test_x").run(result)
    AsyncTests("test_x").run(result)
    assert result.wasSuccessful()
    assert seen == {
        "cleanup": (True, "Cleanups"),
        "asyncSetUp": (True, "Async case"),
        "asyncTearDown": (True, "Async case"),
        "async cleanup": (True, "Async case"),
    }


def _lookups():
    return tuple(_overrides.lookup(name) for name in ("SITE_NAME", "PAGE_SIZE", "MAX_RETRIES"))


def test_a_block_inside_a_decorated_generator_holds_across_its_yields():
    # Fix round: the wrapper's per-step reset dropped the block after the first yield.
    def body():
        with override_configs(SITE_NAME="Inner", PAGE_SIZE=5):
            yield _lookups()
            yield _lookups()
        yield _lookups()

    def run(generator_function):
        seen, between = [], []
        for item in generator_function():
            seen.append(item)
            between.append(dict(_overrides.current()))
        return seen, between

    seen, between = run(override_configs(SITE_NAME="Outer", MAX_RETRIES=1)(body))
    assert seen == [
        ((True, "Inner"), (True, 5), (True, 1)),
        ((True, "Inner"), (True, 5), (True, 1)),
        ((True, "Outer"), (False, None), (True, 1)),
    ]
    # Between items the caller sees what an undecorated generator shows it: the generator's own open block, and none
    # of the decorator's values.
    assert between == run(body)[1] == [{"SITE_NAME": "Inner", "PAGE_SIZE": 5}] * 2 + [{}]
    assert dict(_overrides.current()) == {}


def test_a_block_inside_a_decorated_async_generator_holds_across_its_yields():
    async def body():
        with override_configs(SITE_NAME="Inner", PAGE_SIZE=5):
            await asyncio.sleep(0)
            yield _lookups()
            await asyncio.sleep(0)
            yield _lookups()
        yield _lookups()

    async def run(generator_function):
        seen, between = [], []
        async for item in generator_function():
            seen.append(item)
            between.append(dict(_overrides.current()))
        return seen, between, dict(_overrides.current())

    seen, between, after = asyncio.run(run(override_configs(SITE_NAME="Outer", MAX_RETRIES=1)(body)))
    assert seen == [
        ((True, "Inner"), (True, 5), (True, 1)),
        ((True, "Inner"), (True, 5), (True, 1)),
        ((True, "Outer"), (False, None), (True, 1)),
    ]
    assert between == asyncio.run(run(body))[1] == [{"SITE_NAME": "Inner", "PAGE_SIZE": 5}] * 2 + [{}]
    assert after == {}


def test_a_decorated_context_manager_function_keeps_its_block_for_the_with_body():
    seen = {}

    @contextmanager
    @override_configs(SITE_NAME="Outer")
    def scenario():
        with override_configs(PAGE_SIZE=5):
            yield
            seen["teardown"] = _lookups()

    with scenario():
        seen["with body"] = _lookups()
    assert seen == {
        "with body": ((False, None), (True, 5), (False, None)),
        "teardown": ((True, "Outer"), (True, 5), (False, None)),
    }
    assert dict(_overrides.current()) == {}


def test_an_abandoned_decorated_generator_leaves_nothing_behind():
    @override_configs(SITE_NAME="Outer")
    def generator():
        with override_configs(PAGE_SIZE=5):
            yield

    items = generator()
    next(items)
    del items  # closed at once, which ends its block
    assert dict(_overrides.current()) == {}
    assert override_configs._TOKENS.get({}) == {}


def test_decorated_generators_pass_on_send_throw_close_and_return():
    events = []

    @override_configs(SITE_NAME="Generator")
    def echo():
        try:
            while True:
                try:
                    events.append(((yield "ready"), _overrides.lookup("SITE_NAME")))
                except ValueError:
                    events.append(("thrown", _overrides.lookup("SITE_NAME")))
        finally:
            events.append(("closed", _overrides.lookup("SITE_NAME")))

    items = echo()
    assert next(items) == "ready"
    assert items.send("sent") == "ready"
    assert items.throw(ValueError("boom")) == "ready"
    items.close()
    assert events == [
        ("sent", (True, "Generator")),
        ("thrown", (True, "Generator")),
        ("closed", (True, "Generator")),
    ]

    @override_configs(SITE_NAME="Generator")
    def returns():
        yield
        return _overrides.lookup("SITE_NAME")

    def delegate():
        return (yield from returns())

    items = delegate()
    next(items)
    with pytest.raises(StopIteration) as stop:
        next(items)
    assert stop.value.value == (True, "Generator")


def test_decorated_async_generators_pass_on_asend_athrow_and_aclose():
    events = []

    @override_configs(SITE_NAME="Async generator")
    async def echo():
        try:
            while True:
                try:
                    events.append(((yield "ready"), _overrides.lookup("SITE_NAME")))
                except ValueError:
                    events.append(("thrown", _overrides.lookup("SITE_NAME")))
        finally:
            events.append(("closed", _overrides.lookup("SITE_NAME")))

    async def scenario():
        items = echo()
        assert await anext(items) == "ready"
        assert await items.asend("sent") == "ready"
        assert await items.athrow(ValueError("boom")) == "ready"
        await items.aclose()

    asyncio.run(scenario())
    assert events == [
        ("sent", (True, "Async generator")),
        ("thrown", (True, "Async generator")),
        ("closed", (True, "Async generator")),
    ]


def test_overrides_in_one_thread_are_invisible_in_another():
    # F15. The other thread is already running when the overrides are set, so this holds whatever context new
    # threads start with; both checks run while both threads' overrides are in place.
    main_entered = threading.Event()
    thread_entered = threading.Event()
    main_checked = threading.Event()
    seen = {}

    def other_thread():
        main_entered.wait()
        with override_configs(MAX_RETRIES=7):
            seen["other thread"] = (_overrides.lookup("SITE_NAME"), _overrides.lookup("MAX_RETRIES"))
            thread_entered.set()
            main_checked.wait()

    thread = threading.Thread(target=other_thread)
    thread.start()
    with override_configs(SITE_NAME="Main thread"):
        main_entered.set()
        thread_entered.wait()
        seen["main thread"] = (_overrides.lookup("SITE_NAME"), _overrides.lookup("MAX_RETRIES"))
        main_checked.set()
    thread.join()
    assert seen == {
        "other thread": ((False, None), (True, 7)),
        "main thread": ((True, "Main thread"), (False, None)),
    }
