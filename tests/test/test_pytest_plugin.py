import dynamic_configs


def test_the_fixture_sets_overrides_for_the_test(config_overrides):
    config_overrides.set(SITE_NAME="Example")
    config_overrides.set(MAX_RETRIES=3)
    assert dynamic_configs.get("SITE_NAME") == "Example"
    assert dynamic_configs.get("MAX_RETRIES") == 3


def test_the_fixture_clears_overrides_after_each_test(pytester):
    pytester.makepyfile(
        """
        from dynamic_configs import _overrides

        def test_sets(config_overrides):
            config_overrides.set(SITE_NAME="Example")
            assert _overrides.lookup("SITE_NAME") == (True, "Example")

        def test_cleared_afterwards():
            assert _overrides.lookup("SITE_NAME") == (False, None)
        """
    )
    # The inner run has no Django settings, and the fixture doesn't need them. It runs in this process, where
    # pytest-playwright (when installed, for the browser tests) already holds its one assertion scope open.
    result = pytester.runpytest("-p", "no:django", "-p", "no:playwright")
    result.assert_outcomes(passed=2)
