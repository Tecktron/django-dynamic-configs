"""The suite against a real cache server (``DYNAMIC_CONFIGS_TEST_CACHE``), and the switch and guard that select it.

The settings and guard tests run everywhere; the rest need a server, so they skip unless the variable is set.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import warnings
from pathlib import Path

import pytest
from django.core.cache import CacheKeyWarning, caches
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

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
    # Over Memcached's default 1 MB item limit, so the server refuses the create's cache write and each read's cache
    # fill (run here by executing the on-commit callbacks): the second read follows a failed fill. What gets logged
    # depends on the client, so it isn't asserted: Django's memcached set deletes the key without raising when the
    # client only reports failure, while pymemcache raises (logged as a failed cache write).
    big = "x" * (2 * 1024 * 1024)
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.get_or_create("BIG_TEXT", "text", big)
    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
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
    mocker.patch("tests.real_cache.lock_server", return_value=True)
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
    mocker.patch("tests.real_cache.lock_server", return_value=True)
    mocker.patch("tests.real_cache.server_holds_data", side_effect=ConnectionError)
    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_sessionstart(request.session)
    assert exit_info.value.msg == "Can't reach the redis server at redis://127.0.0.1:16379/0."
    assert exit_info.value.returncode == 3


@pytest.fixture
def locks(mocker, monkeypatch, tmp_path):
    """Lock files in a directory of this test's own, so a real run's lock is never touched; closed afterwards."""
    monkeypatch.setenv("DYNAMIC_CONFIGS_TEST_REDIS_URL", "redis://127.0.0.1:16379/0")
    mocker.patch("tests.real_cache.TEST_CACHE", "redis")
    mocker.patch("tests.real_cache.LOCK_DIR", tmp_path)
    held = mocker.patch("tests.real_cache._held_locks", [])
    yield held
    for file in held:
        file.close()


flock_only = pytest.mark.skipif(
    real_cache.fcntl is None, reason="the server lock is POSIX-only (flock): without fcntl, as on Windows, there's none"
)


@flock_only
def test_a_second_run_cannot_take_the_server_lock(locks):
    assert real_cache.lock_server()
    # A second open of the same file stands in for a second process: flock locks belong to the open file.
    assert not real_cache.lock_server()
    assert len(locks) == 1


@flock_only
def test_closing_the_lock_file_releases_the_lock(locks):
    assert real_cache.lock_server()
    locks.pop().close()
    assert real_cache.lock_server()


def test_each_address_has_its_own_lock(locks, monkeypatch):
    assert real_cache.lock_server()
    monkeypatch.setenv("DYNAMIC_CONFIGS_TEST_REDIS_URL", "redis://127.0.0.1:16379/1")
    assert real_cache.lock_server()


@flock_only
def test_a_server_in_use_by_another_run_stops_the_run(locks, mocker, request):
    holds_data = mocker.patch("tests.real_cache.server_holds_data", return_value=False)
    assert real_cache.lock_server()
    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_sessionstart(request.session)
    assert exit_info.value.msg == (
        "Another test run is using the redis server at redis://127.0.0.1:16379/0; the tests empty it, so two runs "
        "can't share it. Nothing was deleted."
    )
    assert exit_info.value.returncode == 3
    holds_data.assert_not_called()


@real_server_only
def test_the_guard_sees_data_it_did_not_write():
    assert not real_cache.server_holds_data()
    client = real_cache.raw_client()
    client.set("someone-else", "x")
    try:
        assert real_cache.server_holds_data()
    finally:
        client.delete("someone-else")


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
READ_TIMEOUT = 30


class Reader:
    """A second process (``tests.cross_process_reader``) that reads settings through the shared cache and database."""

    def __init__(self, process):
        self.process = process

    def ask(self, name):
        """Send ``name`` to the process and return its JSON reply, failing the test if it takes over ``READ_TIMEOUT``."""
        try:
            self.process.stdin.write(name + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            pytest.fail(f"The second process has ended: {self.process.stderr.read()}")
        line = []
        reader = threading.Thread(target=lambda: line.append(self.process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(READ_TIMEOUT)
        if reader.is_alive():
            pytest.fail(f"The second process didn't answer for {name!r} within {READ_TIMEOUT} seconds.")
        if not line[0]:
            pytest.fail(f"The second process ended without answering for {name!r}: {self.process.stderr.read()}")
        return json.loads(line[0])


@pytest.fixture
def reader():
    """The second process, started once for the test and closed afterwards."""
    environment = {**os.environ, "DYNAMIC_CONFIGS_TEST_SHARED_DB": connection.settings_dict["NAME"]}
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.cross_process_reader"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield Reader(process)
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:  # The process has already ended.
            pass
        try:
            process.wait(timeout=READ_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()


@real_server_only
@pytest.mark.django_db(transaction=True)
def test_a_second_process_sees_creates_updates_and_deletes(reader):
    dynamic_configs.get_or_create("SITE_NAME", "str", "First")
    # Drop the entry the create cached, so the second process has to read the shared database and fill the cache; the
    # update then replaces an entry the second process wrote.
    cache.delete("SITE_NAME")
    assert reader.ask("SITE_NAME") == {"get": "First", "cached": "('str', 'First')"}
    dynamic_configs.update("SITE_NAME", "Second")
    assert reader.ask("SITE_NAME") == {"get": "Second", "cached": "('str', 'Second')"}
    dynamic_configs.delete("SITE_NAME")
    assert reader.ask("SITE_NAME") == {"get": None, "cached": "ABSENT"}
