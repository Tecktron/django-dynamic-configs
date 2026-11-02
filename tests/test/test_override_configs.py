import asyncio

import pytest

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
