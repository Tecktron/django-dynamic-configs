"""A cache backend whose every operation fails, like an unreachable Redis."""

from django.core.cache.backends.base import BaseCache


class FailingCache(BaseCache):
    def __init__(self, location, params):
        super().__init__(params)

    def get(self, key, default=None, version=None):
        raise ConnectionError("cache down")

    def set(self, key, value, timeout=None, version=None):
        raise ConnectionError("cache down")

    def delete(self, key, version=None):
        raise ConnectionError("cache down")
