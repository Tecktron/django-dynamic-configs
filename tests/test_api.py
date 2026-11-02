import logging
from unittest import mock

import pytest
from django.db import DatabaseError

import dynamic_configs
from dynamic_configs import _overrides, cache
from dynamic_configs.exceptions import ConfigValueError
from dynamic_configs.models import Config, ConfigDoesNotExist

pytestmark = pytest.mark.django_db


def make(name="SITE_NAME", type_key="str", value="Example", **fields):
    return Config.objects.create(name=name, type=type_key, value=value, **fields)


def test_get_returns_the_typed_value():
    make("MAX_RETRIES", "int", "3")
    assert dynamic_configs.get("MAX_RETRIES") == 3


def test_get_caches_what_it_reads():
    make()
    dynamic_configs.get("SITE_NAME")
    assert cache.read("SITE_NAME") == ("str", "Example")


def test_get_uses_the_cache_without_querying(django_assert_num_queries):
    cache.write("SITE_NAME", ("str", "Cached"))
    with django_assert_num_queries(0):
        assert dynamic_configs.get("SITE_NAME") == "Cached"


def test_no_cache_reads_the_database_and_refreshes_the_cache():
    make(value="Fresh")
    cache.write("SITE_NAME", ("str", "Stale"))
    assert dynamic_configs.get("SITE_NAME", no_cache=True) == "Fresh"
    assert cache.read("SITE_NAME") == ("str", "Fresh")


def test_a_missing_setting_raises_without_a_default():
    with pytest.raises(ConfigDoesNotExist, match="'MISSING' does not exist"):
        dynamic_configs.get("MISSING")


def test_a_missing_setting_returns_the_default():
    assert dynamic_configs.get("MISSING", default=5) == 5


def test_a_missing_setting_is_cached_as_absent(django_assert_num_queries):
    dynamic_configs.get("MISSING", default=None)
    with django_assert_num_queries(0):
        assert dynamic_configs.get("MISSING", default=7) == 7


def test_an_empty_allow_null_setting_returns_none():
    make(value=None, allow_null=True)
    assert dynamic_configs.get("SITE_NAME") is None


def test_invalid_names_are_missing_without_touching_cache_or_database(settings, caplog, django_assert_num_queries):
    # Review focus: names that can't exist never reach the cache (memcached rejects keys with spaces) or the database.
    settings.DYNAMIC_CONFIGS = {"CACHE": "failing"}
    with django_assert_num_queries(0):
        assert dynamic_configs.get("site name", default=1) == 1
        with pytest.raises(ConfigDoesNotExist):
            dynamic_configs.get(42)
    assert caplog.records == []


def test_a_database_error_without_a_default_propagates():
    with mock.patch("dynamic_configs.api._load_entry", side_effect=DatabaseError("down")), pytest.raises(DatabaseError):
        dynamic_configs.get("SITE_NAME")


def test_a_database_error_with_a_default_logs_a_warning(caplog):
    with mock.patch("dynamic_configs.api._load_entry", side_effect=DatabaseError("down")):
        assert dynamic_configs.get("SITE_NAME", default="fallback") == "fallback"
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "Database read failed for config 'SITE_NAME'; returning the default"
    assert record.config_name == "SITE_NAME"


def test_cache_errors_fall_through_to_the_database(settings, caplog):
    settings.DYNAMIC_CONFIGS = {"CACHE": "failing"}
    make()
    assert dynamic_configs.get("SITE_NAME") == "Example"
    assert "Cache read failed for config 'SITE_NAME'" in caplog.text


def test_an_unreadable_value_raises_without_a_default():
    make("MAX_RETRIES", "int", "three")
    with pytest.raises(ConfigValueError, match="'MAX_RETRIES' can't be read"):
        dynamic_configs.get("MAX_RETRIES")


def test_an_unreadable_value_returns_the_default_and_logs_an_error(caplog):
    make("MAX_RETRIES", "int", "three")
    assert dynamic_configs.get("MAX_RETRIES", default=1) == 1
    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert record.getMessage() == "Config 'MAX_RETRIES' can't be read (type 'int'); returning the default"
    assert record.config_type == "int"
    assert "three" not in record.getMessage()


def test_an_unregistered_type_raises_without_a_default():
    # Review focus: the stored type was removed from DYNAMIC_CONFIGS["TYPES"].
    make("THEME", "gone", "dark")
    with pytest.raises(ConfigValueError, match="'gone', which isn't registered"):
        dynamic_configs.get("THEME")


def test_an_unregistered_type_returns_the_default(caplog):
    make("THEME", "gone", "dark")
    assert dynamic_configs.get("THEME", default="light") == "light"
    assert caplog.records[0].levelno == logging.ERROR


def test_overrides_win_without_touching_cache_or_database(django_assert_num_queries):
    make()
    token = _overrides.push({"SITE_NAME": "Overridden"})
    try:
        with django_assert_num_queries(0):
            assert dynamic_configs.get("SITE_NAME") == "Overridden"
    finally:
        _overrides.pop(token)


def test_a_logging_handler_that_reads_configs_does_not_recurse(settings):
    # Review focus: only the outer get logs; the handler's own get is silenced by the re-entrancy guard.
    settings.DYNAMIC_CONFIGS = {"CACHE": "failing"}

    class ReadingHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.messages = []

        def emit(self, record):
            self.messages.append(record.getMessage())
            dynamic_configs.get("OTHER", default=None)

    handler = ReadingHandler()
    package_logger = logging.getLogger("dynamic_configs")
    package_logger.addHandler(handler)
    try:
        assert dynamic_configs.get("SITE_NAME", default="fallback") == "fallback"
    finally:
        package_logger.removeHandler(handler)
    assert handler.messages == [
        "Cache read failed for config 'SITE_NAME'; reading from the database",
        "Cache write failed for config 'SITE_NAME'; any old entry expires after the cache timeout",
    ]
