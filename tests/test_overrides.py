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


def test_restore_puts_back_a_snapshot():
    before = _overrides.snapshot()
    _overrides.pin({"SITE_NAME": "Pinned"})
    try:
        assert dict(_overrides.current()) == {"SITE_NAME": "Pinned"}
    finally:
        _overrides.restore(before)
    assert _overrides.lookup("SITE_NAME") == (False, None)


def test_a_pin_outlasts_the_block_open_when_it_is_added():
    before = _overrides.snapshot()
    try:
        block = _overrides.push({"SITE_NAME": "Block", "MAX_RETRIES": 1})
        _overrides.pin({"SITE_NAME": "Pinned"})
        assert _overrides.lookup("SITE_NAME") == (True, "Pinned")
        _overrides.pop(block)
        assert dict(_overrides.current()) == {"SITE_NAME": "Pinned"}
        # A block opened after the pin wins while it's open, and leaves the pin in place.
        later = _overrides.push({"SITE_NAME": "Later"})
        assert _overrides.lookup("SITE_NAME") == (True, "Later")
        _overrides.pop(later)
        assert dict(_overrides.current()) == {"SITE_NAME": "Pinned"}
    finally:
        _overrides.restore(before)


def test_pop_drops_a_block_left_open_above_it():
    # Blocks should end in order; if an inner one didn't, the outer one's end still takes it away.
    outer = _overrides.push({"SITE_NAME": "Outer"})
    _overrides.push({"MAX_RETRIES": 1})
    _overrides.pop(outer)
    assert dict(_overrides.current()) == {}


def test_attach_and_detach_switch_a_layer_under_the_layers_above_it():
    before = _overrides.snapshot()
    try:
        own = _overrides.make_layer({"SITE_NAME": "Own", "MAX_RETRIES": 1})
        _overrides.attach(own, ())
        _overrides.push({"SITE_NAME": "Above"})
        above = _overrides.detach(own)
        assert dict(_overrides.current()) == {"SITE_NAME": "Above"}
        _overrides.attach(own, above)
        # Back under the layer that was above it, so that one still wins.
        assert dict(_overrides.current()) == {"SITE_NAME": "Above", "MAX_RETRIES": 1}
        assert _overrides.detach(own) == above
        # Detaching a layer that isn't active changes nothing.
        assert _overrides.detach(own) == ()
        assert dict(_overrides.current()) == {"SITE_NAME": "Above"}
    finally:
        _overrides.restore(before)
