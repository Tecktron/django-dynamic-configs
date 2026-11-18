import dynamic_configs
from dynamic_configs import _overrides
from dynamic_configs.test import override_configs


def test_the_fixture_sets_overrides_for_the_test(config_overrides):
    config_overrides.set(SITE_NAME="Example")
    config_overrides.set(MAX_RETRIES=3)
    assert dynamic_configs.get("SITE_NAME") == "Example"
    assert dynamic_configs.get("MAX_RETRIES") == 3


def test_the_fixture_clears_overrides_after_each_test(pytester):
    pytester.makepyfile(
        """
        from dynamic_configs import _overrides

        from dynamic_configs.test import override_configs

        def test_sets(config_overrides):
            with override_configs(MAX_RETRIES=1):
                config_overrides.set(SITE_NAME="Example")
            assert _overrides.lookup("SITE_NAME") == (True, "Example")

        def test_cleared_afterwards():
            assert _overrides.current() == {}
        """
    )
    # The inner run has no Django settings, and the fixture doesn't need them. It runs in this process, where
    # pytest-playwright (when installed, for the browser tests) already holds its one assertion scope open.
    result = pytester.runpytest("-p", "no:django", "-p", "no:playwright")
    result.assert_outcomes(passed=2)


def test_set_inside_a_with_block_lasts_for_the_rest_of_the_test(config_overrides):
    # F13: the block's end put back the overrides from before it, dropping what set() had added.
    with override_configs(SITE_NAME="Block", MAX_RETRIES=1):
        config_overrides.set(SITE_NAME="Set")
        # The latest wins: set() beats a block opened before it.
        assert dynamic_configs.get("SITE_NAME") == "Set"
    assert _overrides.lookup("SITE_NAME") == (True, "Set")
    assert _overrides.lookup("MAX_RETRIES") == (False, None)


def test_a_block_opened_after_set_wins_while_it_is_open(config_overrides):
    config_overrides.set(SITE_NAME="Set")
    with override_configs(SITE_NAME="Block"):
        assert dynamic_configs.get("SITE_NAME") == "Block"
    assert dynamic_configs.get("SITE_NAME") == "Set"


@override_configs(SITE_NAME="Class", MAX_RETRIES=1)
class TestSetInADecoratedClass:
    def test_set_wins_over_the_class_value(self, config_overrides):
        config_overrides.set(SITE_NAME="Set")
        assert dynamic_configs.get("SITE_NAME") == "Set"
        assert dynamic_configs.get("MAX_RETRIES") == 1


def test_set_inside_a_decorated_generator_lasts_after_it(config_overrides):
    @override_configs(SITE_NAME="Decorator")
    def generator():
        config_overrides.set(SITE_NAME="Set", PAGE_SIZE=10)
        yield
        # The latest wins, over the decorator's values too.
        yield _overrides.lookup("SITE_NAME")

    assert list(generator()) == [None, (True, "Set")]
    assert dict(_overrides.current()) == {"SITE_NAME": "Set", "PAGE_SIZE": 10}
