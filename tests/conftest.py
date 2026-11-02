import pytest
from django.core.cache import caches


@pytest.fixture(autouse=True)
def _clear_caches():
    """Start and end every test with an empty cache, so cached configs don't leak between tests."""
    caches["default"].clear()
    yield
    caches["default"].clear()
