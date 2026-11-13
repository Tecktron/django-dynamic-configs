"""Run the suite against a real cache server, chosen by ``DYNAMIC_CONFIGS_TEST_CACHE``.

The suite empties the default cache around every test (``FLUSHDB`` on Redis, the whole server on Memcached), so the
server's address has no default, and a run stops before the first test if another run is using the server, or it
already holds anything.
"""

import hashlib
import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

try:
    import fcntl
except ImportError:  # Windows: no flock, so runs there aren't protected against each other.
    fcntl = None

TEST_CACHE = os.environ.get("DYNAMIC_CONFIGS_TEST_CACHE") or None
LOCK_DIR = Path(tempfile.gettempdir())
# The lock files this process holds: open, so locked, until it exits.
_held_locks = []

# For each value of DYNAMIC_CONFIGS_TEST_CACHE: the backend, the variable holding the address, and any OPTIONS.
_CACHES = {
    "redis": ("django.core.cache.backends.redis.RedisCache", "DYNAMIC_CONFIGS_TEST_REDIS_URL", {}),
    "redis-json": (
        "django_redis.cache.RedisCache",
        "DYNAMIC_CONFIGS_TEST_REDIS_URL",
        {"SERIALIZER": "django_redis.serializers.json.JSONSerializer"},
    ),
    "memcached": ("django.core.cache.backends.memcached.PyMemcacheCache", "DYNAMIC_CONFIGS_TEST_MEMCACHED", {}),
}


def _selected(name: str | None) -> tuple[str, str, dict]:
    """Return the backend, address and options of the cache ``name``."""
    if name not in _CACHES:
        raise ImproperlyConfigured(
            f"DYNAMIC_CONFIGS_TEST_CACHE is {name!r}; use one of {', '.join(_CACHES)}, or leave it unset."
        )
    backend, variable, options = _CACHES[name]
    location = os.environ.get(variable)
    if not location:
        raise ImproperlyConfigured(
            f"DYNAMIC_CONFIGS_TEST_CACHE={name} needs {variable}, the address of a server the tests may empty."
        )
    return backend, location, options


def cache_settings() -> dict:
    """Return the ``CACHES["default"]`` entry for the requested cache.

    :raises ImproperlyConfigured: ``DYNAMIC_CONFIGS_TEST_CACHE`` isn't a known cache, or its address variable is unset
    """
    backend, location, options = _selected(os.environ.get("DYNAMIC_CONFIGS_TEST_CACHE"))
    entry = {"BACKEND": backend, "LOCATION": location}
    if options:
        entry["OPTIONS"] = options
    return entry


def address() -> str:
    """Return the address of the server in use, for messages."""
    return _selected(TEST_CACHE)[1]


def lock_server() -> bool:
    """Take the advisory lock on the server in use, held until the process exits.

    The lock is a file in ``LOCK_DIR`` named from a hash of the address, locked with ``flock``. A second run against
    the same address finds it held: the two runs' flushes would empty each other's cache.

    :returns: False if another run holds the lock; True once taken, or where ``fcntl`` doesn't exist (Windows)
    """
    if fcntl is None:
        return True
    digest = hashlib.sha256(address().encode()).hexdigest()[:16]
    file = (LOCK_DIR / f"dynamic-configs-tests-{digest}.lock").open("a")
    try:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        file.close()
        return False
    _held_locks.append(file)
    return True


def raw_client():
    """Return a client for the server in use, redis-py's or pymemcache's, without going through Django."""
    location = address()
    if TEST_CACHE == "memcached":
        from pymemcache.client.base import Client

        # Wait for each reply: without it, a write may not have reached the server when another connection looks.
        return Client(location, connect_timeout=5, timeout=5, default_noreply=False)
    import redis

    return redis.Redis.from_url(location, socket_connect_timeout=5, socket_timeout=5)


def server_holds_data() -> bool:
    """Return True if the server already holds anything: Redis's ``DBSIZE`` for the URL's database, or Memcached's
    ``curr_items``.

    :raises ConnectionError: the server can't be reached
    """
    client = raw_client()
    if TEST_CACHE == "memcached":
        try:
            return int(client.stats()[b"curr_items"]) > 0
        except OSError as error:
            raise ConnectionError(str(error)) from error
        finally:
            client.close()
    import redis

    try:
        return client.dbsize() > 0
    except (redis.ConnectionError, redis.TimeoutError) as error:
        raise ConnectionError(str(error)) from error
    finally:
        client.close()
