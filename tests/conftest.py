import os

import pytest
from django.core.cache import caches

# The integration's tests import simple_history, which only the extras environment installs.
collect_ignore = [] if os.environ.get("DYNAMIC_CONFIGS_TEST_EXTRAS") == "1" else ["contrib"]


@pytest.fixture(autouse=True)
def _clear_caches():
    """Start and end every test with an empty cache, so cached configs don't leak between tests."""
    caches["default"].clear()
    yield
    caches["default"].clear()
