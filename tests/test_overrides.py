from dynamic_configs import _overrides


def test_nothing_is_overridden_by_default():
    assert dict(_overrides.current()) == {}
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_push_layers_values_and_pop_restores():
    outer = _overrides.push({"SITE_NAME": "Outer", "MAX_RETRIES": 3})
    inner = _overrides.push({"SITE_NAME": "Inner"})
    assert _overrides.lookup("SITE_NAME") == (True, "Inner")
    assert _overrides.lookup("MAX_RETRIES") == (True, 3)
    _overrides.pop(inner)
    assert _overrides.lookup("SITE_NAME") == (True, "Outer")
    _overrides.pop(outer)
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_none_is_a_real_override():
    token = _overrides.push({"SITE_NAME": None})
    try:
        assert _overrides.lookup("SITE_NAME") == (True, None)
    finally:
        _overrides.pop(token)


def test_replace_sets_the_whole_mapping():
    previous = _overrides.current()
    _overrides.replace({"SITE_NAME": "Replaced"})
    try:
        assert dict(_overrides.current()) == {"SITE_NAME": "Replaced"}
    finally:
        _overrides.replace(previous)
    assert _overrides.lookup("SITE_NAME") == (False, None)
