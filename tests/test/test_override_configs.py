import asyncio

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
