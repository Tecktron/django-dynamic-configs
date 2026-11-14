import os

import pytest
from django.core.cache import caches

from tests import real_cache

# The integration's tests import simple_history, which only the extras environment installs.
collect_ignore = [] if os.environ.get("DYNAMIC_CONFIGS_TEST_EXTRAS") == "1" else ["contrib"]


def pytest_sessionstart(session):
    """Before any test empties the cache, stop the run if another run is using the real server, or it already holds
    data, or can't be reached."""
    if not real_cache.TEST_CACHE:
        return
    if not real_cache.lock_server():
        pytest.exit(
            f"Another test run is using the {real_cache.TEST_CACHE} server at {real_cache.address()}; the tests empty "
            "it, so two runs can't share it. Nothing was deleted.",
            returncode=3,
        )
    try:
        holds_data = real_cache.server_holds_data()
    except ConnectionError:
        pytest.exit(f"Can't reach the {real_cache.TEST_CACHE} server at {real_cache.address()}.", returncode=3)
    if holds_data:
        pytest.exit(
            f"The {real_cache.TEST_CACHE} server at {real_cache.address()} already holds data; the tests empty it, so "
            "they won't run against it. Nothing was deleted. Start a fresh server.",
            returncode=3,
        )


@pytest.fixture(autouse=True)
def _clear_caches():
    """Start and end every test with an empty cache, so cached configs don't leak between tests."""
    caches["default"].clear()
    yield
    caches["default"].clear()
