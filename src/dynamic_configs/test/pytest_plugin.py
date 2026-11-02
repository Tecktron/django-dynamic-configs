"""pytest plugin providing the ``config_overrides`` fixture; loaded automatically when the package is installed.

It imports nothing from Django when pytest starts, so it works in projects whose Django settings load later.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from dynamic_configs import _overrides


class ConfigOverrides:
    """Set config overrides that last until the end of the current test."""

    def __init__(self) -> None:
        """Remember the overrides active before the test."""
        self._previous = _overrides.current()

    def set(self, **values: Any) -> None:
        """Override configs by name for the rest of the test."""
        _overrides.replace({**_overrides.current(), **values})

    def restore(self) -> None:
        """Put back the overrides active before the test."""
        # replace() rather than a push/pop token: the test may run in a different context than the fixture's
        # setup (for example an async test), and a token can only be reset in the context that created it.
        _overrides.replace(self._previous)


@pytest.fixture
def config_overrides() -> Iterator[ConfigOverrides]:
    """Override config values for one test: ``config_overrides.set(SITE_NAME="Example")``."""
    overrides = ConfigOverrides()
    yield overrides
    overrides.restore()
