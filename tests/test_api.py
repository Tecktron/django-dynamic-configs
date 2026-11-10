import logging
from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.db import DatabaseError, transaction

import dynamic_configs
from dynamic_configs import _overrides, cache
from dynamic_configs.exceptions import ConfigTypeError, ConfigValueError
from dynamic_configs.models import Config, ConfigDoesNotExist

pytestmark = pytest.mark.django_db


def make(name="SITE_NAME", type_key="str", value="Example", **fields):
    return Config.objects.create(name=name, type=type_key, value=value, **fields)


def test_get_returns_the_typed_value():
    make("MAX_RETRIES", "int", "3")
    assert dynamic_configs.get("MAX_RETRIES") == 3


def test_get_caches_what_it_reads_once_committed(django_capture_on_commit_callbacks):
    make()
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.get("SITE_NAME")
    assert cache.read("SITE_NAME") == ("str", "Example")


def test_get_uses_the_cache_without_querying(django_assert_num_queries):
    cache.write("SITE_NAME", ("str", "Cached"))
    with django_assert_num_queries(0):
        assert dynamic_configs.get("SITE_NAME") == "Cached"


def test_no_cache_reads_the_database_and_refreshes_the_cache(django_capture_on_commit_callbacks):
    make(value="Fresh")
    cache.write("SITE_NAME", ("str", "Stale"))
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get("SITE_NAME", no_cache=True) == "Fresh"
    assert cache.read("SITE_NAME") == ("str", "Fresh")


def test_a_missing_setting_raises_without_a_default():
    with pytest.raises(ConfigDoesNotExist, match="'MISSING' does not exist"):
        dynamic_configs.get("MISSING")


def test_a_missing_setting_returns_the_default():
    assert dynamic_configs.get("MISSING", default=5) == 5


def test_a_missing_setting_is_cached_as_absent(django_assert_num_queries, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
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
        # Review: an unhashable name raised TypeError from the override lookup, despite the default.
        assert dynamic_configs.get(["SITE_NAME"], default=1) == 1
    assert caplog.records == []


def test_a_database_error_without_a_default_propagates(mocker):
    mocker.patch("dynamic_configs.api._load_entry", side_effect=DatabaseError("down"))
    with pytest.raises(DatabaseError):
        dynamic_configs.get("SITE_NAME")


def test_a_database_error_with_a_default_logs_a_warning(caplog, mocker):
    mocker.patch("dynamic_configs.api._load_entry", side_effect=DatabaseError("down"))
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
    assert record.getMessage() == "Config 'MAX_RETRIES' can't be read (type 'int', ValueError); returning the default"
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


@pytest.mark.django_db(transaction=True)
def test_a_logging_handler_that_reads_configs_does_not_recurse(settings):
    # transaction=True: autocommit, so cache fills happen at once, as in a view outside ATOMIC_REQUESTS.
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


def test_get_or_create_creates_a_missing_setting(caplog):
    caplog.set_level(logging.INFO, logger="dynamic_configs")
    value, created = dynamic_configs.get_or_create("MAX_RETRIES", "int", 3, description="Retries per request.")
    assert (value, created) == (3, True)
    row = Config.objects.get(name="MAX_RETRIES")
    assert (row.type, row.value, row.allow_null, row.description) == ("int", "3", False, "Retries per request.")
    assert "Created config 'MAX_RETRIES' (type 'int')" in caplog.text


def test_get_or_create_returns_an_existing_value_and_refreshes_the_cache(django_capture_on_commit_callbacks):
    make("MAX_RETRIES", "int", "5")
    cache.write("MAX_RETRIES", ("int", "4"))
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get_or_create("MAX_RETRIES", "int", 3) == (5, False)
    assert cache.read("MAX_RETRIES") == ("int", "5")


def test_get_or_create_refuses_an_existing_setting_of_another_type():
    make("MAX_RETRIES", "int", "5")
    with pytest.raises(ConfigTypeError, match="already exists with type 'int', not 'str'"):
        dynamic_configs.get_or_create("MAX_RETRIES", "str", "5")


def test_get_or_create_returns_the_value_as_get_will():
    value, _ = dynamic_configs.get_or_create("STARTS_AT", "datetime", datetime(2026, 11, 2, 17, 0))
    assert value == datetime(2026, 11, 2, 22, 0, tzinfo=dt_timezone.utc)
    assert value.tzinfo is dt_timezone.utc


@pytest.mark.parametrize(
    ("name", "message"), [("max_retries", "UPPER_SNAKE_CASE"), (5, "must be strings"), (["X"], "must be strings")]
)
def test_get_or_create_validates_the_name(name, message):
    with pytest.raises(ConfigValueError, match=message):
        dynamic_configs.get_or_create(name, "int", 3)


def test_get_or_create_needs_a_registered_type():
    with pytest.raises(ConfigTypeError, match="'nope' isn't a registered config type"):
        dynamic_configs.get_or_create("MAX_RETRIES", "nope", 3)


def test_get_or_create_checks_the_value_type():
    with pytest.raises(ConfigTypeError, match="expects int, not str"):
        dynamic_configs.get_or_create("MAX_RETRIES", "int", "3")


def test_get_or_create_reports_serializer_rejections():
    with pytest.raises(ConfigValueError, match="single line"):
        dynamic_configs.get_or_create("SITE_NAME", "str", "two\nlines")


def test_get_or_create_needs_allow_null_for_none():
    with pytest.raises(ConfigTypeError, match="pass allow_null=True"):
        dynamic_configs.get_or_create("SITE_NAME", "str", None)


def test_get_or_create_can_create_an_empty_setting():
    assert dynamic_configs.get_or_create("SITE_NAME", "str", None, allow_null=True) == (None, True)
    row = Config.objects.get(name="SITE_NAME")
    assert row.value is None
    assert row.allow_null


def test_get_or_create_handles_a_concurrent_create(mocker):
    # Another process creates the row between our lookup and our insert.
    make("MAX_RETRIES", "int", "5")
    mocker.patch.object(Config.objects, "get", side_effect=Config.DoesNotExist)
    assert dynamic_configs.get_or_create("MAX_RETRIES", "int", 3) == (5, False)


def test_get_or_create_returns_an_override_without_the_database(django_assert_num_queries):
    token = _overrides.push({"MAX_RETRIES": 9})
    try:
        with django_assert_num_queries(0):
            assert dynamic_configs.get_or_create("MAX_RETRIES", "int", 3) == (9, False)
    finally:
        _overrides.pop(token)


def test_update_changes_the_value(caplog):
    caplog.set_level(logging.INFO, logger="dynamic_configs")
    make("MAX_RETRIES", "int", "3")
    dynamic_configs.update("MAX_RETRIES", 5)
    assert dynamic_configs.get("MAX_RETRIES", no_cache=True) == 5
    assert "Updated config 'MAX_RETRIES'" in caplog.text


def test_update_refreshes_the_cache_on_commit(django_capture_on_commit_callbacks):
    make()
    dynamic_configs.get("SITE_NAME")
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.update("SITE_NAME", "Renamed")
    assert cache.read("SITE_NAME") == ("str", "Renamed")


def test_update_raises_for_a_missing_setting():
    with pytest.raises(ConfigDoesNotExist):
        dynamic_configs.update("MISSING", 1)


def test_update_refuses_an_unregistered_type():
    make("THEME", "gone", "dark")
    with pytest.raises(ConfigValueError, match="isn't registered"):
        dynamic_configs.update("THEME", "light")


def test_update_checks_the_value_type():
    make("MAX_RETRIES", "int", "3")
    with pytest.raises(ConfigTypeError):
        dynamic_configs.update("MAX_RETRIES", "5")


def test_update_to_none_needs_allow_null():
    make()
    with pytest.raises(ConfigTypeError, match="allow_null"):
        dynamic_configs.update("SITE_NAME", None)


def test_update_to_none_when_allowed():
    make(allow_null=True)
    dynamic_configs.update("SITE_NAME", None)
    assert Config.objects.get(name="SITE_NAME").value is None


def test_update_can_turn_allow_null_on_with_the_value():
    make()
    dynamic_configs.update("SITE_NAME", None, allow_null=True)
    row = Config.objects.get(name="SITE_NAME")
    assert (row.value, row.allow_null) == (None, True)


def test_update_can_turn_allow_null_off():
    make(value=None, allow_null=True)
    dynamic_configs.update("SITE_NAME", "Example", allow_null=False)
    row = Config.objects.get(name="SITE_NAME")
    assert (row.value, row.allow_null) == ("Example", False)


def test_update_refuses_none_when_turning_allow_null_off():
    make(allow_null=True)
    with pytest.raises(ConfigTypeError):
        dynamic_configs.update("SITE_NAME", None, allow_null=False)


def test_delete_returns_true_and_logs(caplog):
    caplog.set_level(logging.INFO, logger="dynamic_configs")
    make()
    assert dynamic_configs.delete("SITE_NAME") is True
    assert not Config.objects.filter(name="SITE_NAME").exists()
    assert "Deleted config 'SITE_NAME'" in caplog.text


def test_delete_returns_false_for_a_missing_setting():
    assert dynamic_configs.delete("MISSING") is False


def test_a_deleted_setting_reads_as_missing_after_commit(django_capture_on_commit_callbacks):
    make()
    dynamic_configs.get("SITE_NAME")
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.delete("SITE_NAME")
    assert dynamic_configs.get("SITE_NAME", default=None) is None
    assert cache.read("SITE_NAME") is cache.ABSENT


def test_a_value_too_deeply_nested_to_read_returns_the_default(caplog):
    # Review finding: json.loads raised RecursionError, which escaped get's default guarantee.
    make("DEEP", "json", "[" * 100_000 + "]" * 100_000)
    assert dynamic_configs.get("DEEP", default=[]) == []
    assert caplog.records[0].levelno == logging.ERROR


def test_a_broken_custom_type_does_not_stop_other_configs_being_read(settings):
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {"broken": {"type": "tests.custom_types.Missing", "serializer": "tests.custom_types.ColorSerializer"}}
    }
    make("MAX_RETRIES", "int", "3")
    assert dynamic_configs.get("MAX_RETRIES") == 3


def test_a_read_inside_a_rolled_back_transaction_never_reaches_the_cache(django_capture_on_commit_callbacks):
    # Review finding: get() cached the uncommitted value at once, so every process kept reading it after the rollback.
    make("MAX_RETRIES", "int", "1")
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                dynamic_configs.update("MAX_RETRIES", 2)
                assert dynamic_configs.get("MAX_RETRIES") == 2
                assert dynamic_configs.get_or_create("MAX_RETRIES", "int", 5) == (2, False)
                raise RuntimeError("roll back")
        except RuntimeError:
            pass
    assert cache.read("MAX_RETRIES") is cache.NOT_CACHED
    assert dynamic_configs.get("MAX_RETRIES", no_cache=True) == 1


def test_an_unreadable_value_is_never_written_to_the_log(settings, caplog):
    # Review finding: the ERROR log attached the traceback, whose chained message can contain the stored value.
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {"leaky": {"type": "builtins.str", "serializer": "tests.custom_types.LeakySerializer"}}
    }
    make("API_TOKEN", "leaky", "s3cret-token")
    assert dynamic_configs.get("API_TOKEN", default=None) is None
    [record] = caplog.records
    assert not record.exc_info
    assert "s3cret-token" not in caplog.text
    assert "ValueError" in record.getMessage()
