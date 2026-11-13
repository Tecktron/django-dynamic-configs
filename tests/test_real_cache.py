"""The suite against a real cache server (``DYNAMIC_CONFIGS_TEST_CACHE``), and the switch and guard that select it.

The settings and guard tests run everywhere; the rest need a server, so they skip unless the variable is set.
"""

import logging
import warnings

import pytest
from django.core.cache import CacheKeyWarning, caches
from django.core.exceptions import ImproperlyConfigured

import dynamic_configs
from dynamic_configs import cache
from tests import conftest, real_cache

BACKENDS = {
    "redis": "django.core.cache.backends.redis.RedisCache",
    "redis-json": "django_redis.cache.RedisCache",
    "memcached": "django.core.cache.backends.memcached.PyMemcacheCache",
}

real_server_only = pytest.mark.skipif(
    not real_cache.TEST_CACHE, reason="needs DYNAMIC_CONFIGS_TEST_CACHE and its server"
)
redis_json_only = pytest.mark.skipif(real_cache.TEST_CACHE != "redis-json", reason="only for the redis-json cache")
memcached_only = pytest.mark.skipif(real_cache.TEST_CACHE != "memcached", reason="only for the memcached cache")


@real_server_only
def test_the_default_cache_is_the_server_asked_for():
    backend_class = type(caches["default"])
    assert f"{backend_class.__module__}.{backend_class.__qualname__}" == BACKENDS[real_cache.TEST_CACHE]


@real_server_only
def test_an_entry_reaches_the_server():
    cache.write("SITE_NAME", ("str", "Example"))
    backend = caches["default"]
    key = backend.make_key(cache.cache_key("SITE_NAME", backend))
    client = real_cache.raw_client()
    if real_cache.TEST_CACHE == "memcached":
        assert client.get(key) is not None
    else:
        assert client.exists(key) == 1


@redis_json_only
def test_the_json_serializer_hands_back_a_list():
    cache.write("SITE_NAME", ("str", "Example"))
    backend = caches["default"]
    assert isinstance(backend.get(cache.cache_key("SITE_NAME", backend)), list)
    assert cache.read("SITE_NAME") == ("str", "Example")


@real_server_only
@pytest.mark.django_db
def test_a_255_character_name_is_cached_on_the_server(
    caplog, django_assert_num_queries, django_capture_on_commit_callbacks
):
    name = "A" * 255
    with warnings.catch_warnings():
        warnings.simplefilter("error", CacheKeyWarning)
        with django_capture_on_commit_callbacks(execute=True):
            dynamic_configs.get_or_create(name, "str", "x")
        with django_assert_num_queries(0):
            assert dynamic_configs.get(name) == "x"
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


@memcached_only
@pytest.mark.django_db
def test_a_value_too_big_for_the_server_is_still_returned(django_capture_on_commit_callbacks):
    # Over Memcached's default 1 MB item limit. What gets logged depends on the client, so it isn't asserted: Django's
    # memcached set deletes the key without raising when the client only reports failure, while pymemcache raises
    # (logged as a failed cache write, on every read that tries to cache it).
    big = "x" * (2 * 1024 * 1024)
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.get_or_create("BIG_TEXT", "text", big)
    assert dynamic_configs.get("BIG_TEXT") == big
    assert dynamic_configs.get("BIG_TEXT") == big


def test_cache_settings_reject_an_unknown_backend(monkeypatch):
    monkeypatch.setenv("DYNAMIC_CONFIGS_TEST_CACHE", "memcache")
    with pytest.raises(ImproperlyConfigured):
        real_cache.cache_settings()


@pytest.mark.parametrize(
    ("backend", "variable"),
    [
        ("redis", "DYNAMIC_CONFIGS_TEST_REDIS_URL"),
        ("redis-json", "DYNAMIC_CONFIGS_TEST_REDIS_URL"),
        ("memcached", "DYNAMIC_CONFIGS_TEST_MEMCACHED"),
    ],
)
def test_cache_settings_require_an_address(monkeypatch, backend, variable):
    monkeypatch.setenv("DYNAMIC_CONFIGS_TEST_CACHE", backend)
    monkeypatch.delenv(variable, raising=False)
    with pytest.raises(ImproperlyConfigured):
        real_cache.cache_settings()


def test_a_server_holding_data_stops_the_run(mocker, monkeypatch, request):
    monkeypatch.setenv("DYNAMIC_CONFIGS_TEST_REDIS_URL", "redis://127.0.0.1:16379/0")
    mocker.patch("tests.real_cache.TEST_CACHE", "redis")
    mocker.patch("tests.real_cache.server_holds_data", return_value=True)
    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_sessionstart(request.session)
    assert exit_info.value.msg == (
        "The redis server at redis://127.0.0.1:16379/0 already holds data; the tests empty it, so they won't run "
        "against it. Nothing was deleted. Start a fresh server."
    )
    assert exit_info.value.returncode == 3


def test_an_unreachable_server_stops_the_run(mocker, monkeypatch, request):
    monkeypatch.setenv("DYNAMIC_CONFIGS_TEST_REDIS_URL", "redis://127.0.0.1:16379/0")
    mocker.patch("tests.real_cache.TEST_CACHE", "redis")
    mocker.patch("tests.real_cache.server_holds_data", side_effect=ConnectionError)
    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_sessionstart(request.session)
    assert exit_info.value.msg == "Can't reach the redis server at redis://127.0.0.1:16379/0."
    assert exit_info.value.returncode == 3


@real_server_only
def test_the_guard_sees_data_it_did_not_write():
    assert not real_cache.server_holds_data()
    client = real_cache.raw_client()
    client.set("someone-else", "x")
    try:
        assert real_cache.server_holds_data()
    finally:
        client.delete("someone-else")
