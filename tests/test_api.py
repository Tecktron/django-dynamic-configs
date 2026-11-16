import logging
import threading
from datetime import datetime
from datetime import timezone as dt_timezone
from enum import Enum

import pytest
from django.db import DatabaseError, connections, router, transaction

import dynamic_configs
from dynamic_configs import _overrides, cache
from dynamic_configs.exceptions import ConfigTypeError, ConfigValueError
from dynamic_configs.models import Config, ConfigDoesNotExist
from tests.custom_types import Color

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


def test_no_cache_of_a_missing_setting_caches_the_marker(django_capture_on_commit_callbacks):
    cache.write("MISSING", ("str", "Stale"))
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get("MISSING", None, no_cache=True) is None
    assert cache.read("MISSING") is cache.ABSENT


def test_no_cache_read_caches_the_database_value_at_commit_not_its_own(django_capture_on_commit_callbacks):
    # F17: a slow no_cache read (or get_or_create) refilled with what it had read, overwriting the newer entry a
    # writer cached. It now reads the row again when its transaction commits.
    make(value="Old")
    with django_capture_on_commit_callbacks(execute=False) as slow_reads:
        assert dynamic_configs.get("SITE_NAME", no_cache=True) == "Old"
        assert dynamic_configs.get_or_create("SITE_NAME", "str", "Other") == ("Old", False)
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.update("SITE_NAME", "New")
    for callback in slow_reads:
        callback()
    assert cache.read("SITE_NAME") == ("str", "New")


@pytest.mark.parametrize(
    "read_past_the_cache",
    [
        lambda: dynamic_configs.get("SITE_NAME", no_cache=True),
        lambda: dynamic_configs.get_or_create("SITE_NAME", "str", "Other"),
    ],
    ids=["no_cache", "get_or_create"],
)
def test_a_slow_plain_fill_after_a_read_past_the_cache_keeps_the_new_value(
    read_past_the_cache, django_capture_on_commit_callbacks
):
    # Review: a plain get (inside atomic) reads the old value and defers its add; a writer commits the new one; a read
    # past the cache commits. If that read only dropped the entry, the plain get's add then cached the old value.
    make(value="Old")
    with django_capture_on_commit_callbacks(execute=False) as slow_fill:
        assert dynamic_configs.get("SITE_NAME") == "Old"
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.update("SITE_NAME", "New")
    with django_capture_on_commit_callbacks(execute=True):
        read_past_the_cache()
    for callback in slow_fill:
        callback()
    assert cache.read("SITE_NAME") == ("str", "New")


def test_a_slow_missing_fill_after_get_or_create_keeps_the_created_row(django_capture_on_commit_callbacks):
    # Review: the same with a plain get that read "doesn't exist" before the setting was created.
    with django_capture_on_commit_callbacks(execute=False) as slow_fill:
        assert dynamic_configs.get("SITE_NAME", None) is None
    with django_capture_on_commit_callbacks(execute=True):
        make(value="Created")
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get_or_create("SITE_NAME", "str", "Other") == ("Created", False)
    for callback in slow_fill:
        callback()
    assert cache.read("SITE_NAME") == ("str", "Created")


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
    # Only a hand-edited row can hold this: saving refuses it.
    make("DEEP", "json", "[" * 129 + "]" * 129)
    assert dynamic_configs.get("DEEP", default=[]) == []
    assert caplog.records[0].levelno == logging.ERROR


def test_a_deeply_nested_list_returns_the_default_in_a_thread_with_a_small_stack():
    # Reading it used to overflow a 256 KB stack (a segfault on Python 3.12). It comes from the cache, so the thread
    # needs no database connection.
    cache.write("DEEP", ("list:str", "[" * 100_000 + "]" * 100_000))
    found = []

    def read():
        try:
            found.append(dynamic_configs.get("DEEP", ["default"]))
        finally:
            connections.close_all()

    previous = threading.stack_size(256 * 1024)
    try:
        thread = threading.Thread(target=read)
        thread.start()
        thread.join()
    finally:
        threading.stack_size(previous)
    assert found == [["default"]]


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


class Priority(int, Enum):
    HIGH = 3


def test_update_stores_an_int_subclass_as_its_number():
    make("LEVEL", "int", "1")
    dynamic_configs.update("LEVEL", Priority.HIGH)
    assert Config.objects.get(name="LEVEL").value == "3"
    assert dynamic_configs.get("LEVEL") == 3


def test_get_or_create_refuses_a_lone_surrogate_and_creates_nothing():
    with pytest.raises(ConfigValueError, match="can't be stored"):
        dynamic_configs.get_or_create("SITE_NAME", "str", "\ud800")
    assert not Config.objects.filter(name="SITE_NAME").exists()


def test_the_docs_example_custom_type_saves_through_update_and_get_or_create(settings):
    # Review Focus 1: the custom type in docs/types.md checks its rule in deserialize and serialize returns the text.
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {"color": {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}}
    }
    assert dynamic_configs.get_or_create("BRAND", "color", Color("#1a2b3c")) == (Color("#1a2b3c"), True)
    dynamic_configs.update("BRAND", Color("#ffffff"))
    assert dynamic_configs.get("BRAND") == Color("#ffffff")
    with pytest.raises(ConfigValueError, match="can't be stored: Enter a hex color"):
        dynamic_configs.update("BRAND", Color("red"))
    assert dynamic_configs.get("BRAND") == Color("#ffffff")


@pytest.mark.django_db(transaction=True)
def test_get_with_default_never_raises_with_autocommit_off(caplog):
    # F20: the cache fill's on_commit raised TransactionManagementError outside atomic with autocommit off.
    make("MAX_RETRIES", "int", "3")
    cache.delete("MAX_RETRIES")
    caplog.set_level(logging.DEBUG, logger="dynamic_configs")
    transaction.set_autocommit(False)
    try:
        assert dynamic_configs.get("MAX_RETRIES", 0) == 3
        assert dynamic_configs.get("MAX_RETRIES", 0, no_cache=True) == 3
        assert dynamic_configs.get_or_create("MAX_RETRIES", "int", 1) == (3, False)
    finally:
        transaction.rollback()
        transaction.set_autocommit(True)
    assert cache.read("MAX_RETRIES") is cache.NOT_CACHED
    message = "Left the cache entry for config 'MAX_RETRIES' as it is: autocommit is off outside a transaction"
    assert caplog.text.count(message) == 3


def test_a_non_string_cache_setting_reads_uncached(settings, caplog):
    # F21: a non-string CACHE made every get raise TypeError, default or not.
    make("MAX_RETRIES", "int", "3")
    settings.DYNAMIC_CONFIGS = {"CACHE": 3}
    assert dynamic_configs.get("MAX_RETRIES", 0) == 3
    assert dynamic_configs.get("MAX_RETRIES") == 3
    assert "Cache alias 3 isn't configured; reading configs without a cache" in caplog.text


def test_a_cache_entry_with_an_unhashable_type_is_a_miss(django_capture_on_commit_callbacks):
    # F22: an unhashable type key made get raise TypeError despite a default.
    make("MAX_RETRIES", "int", "2")
    backend = cache.get_cache()
    backend.set(cache.cache_key("MAX_RETRIES", backend), [["int"], "1"])
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get("MAX_RETRIES", 0) == 2


def test_an_unrecognised_cache_entry_is_replaced(django_capture_on_commit_callbacks, django_assert_num_queries):
    # F23: the refill used add, so an unrecognised entry stayed and every get read the database until it expired. The
    # read now drops it, so the usual add fills the slot.
    make("MAX_RETRIES", "int", "2")
    backend = cache.get_cache()
    backend.set(cache.cache_key("MAX_RETRIES", backend), "garbage")
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get("MAX_RETRIES") == 2
    assert cache.read("MAX_RETRIES") == ("int", "2")
    with django_assert_num_queries(0):
        assert dynamic_configs.get("MAX_RETRIES") == 2


def test_a_newer_entry_cached_after_an_unrecognised_one_is_dropped_is_kept(mocker, django_capture_on_commit_callbacks):
    # The refill after an unrecognised entry must not overwrite an entry a writer cached once it was dropped.
    make("MAX_RETRIES", "int", "2")
    backend = cache.get_cache()
    key = cache.cache_key("MAX_RETRIES", backend)
    backend.set(key, "garbage")
    real_delete = backend.delete

    def delete_then_a_writer_caches(*args, **kwargs):
        result = real_delete(*args, **kwargs)
        backend.set(key, ("int", "3"))
        return result

    mocker.patch.object(backend, "delete", side_effect=delete_then_a_writer_caches)
    with django_capture_on_commit_callbacks(execute=True):
        assert dynamic_configs.get("MAX_RETRIES") == 2
    assert cache.read("MAX_RETRIES") == ("int", "3")


reads_past_the_cache = pytest.mark.parametrize(
    "read_past_the_cache",
    [
        lambda: dynamic_configs.get("SITE_NAME", no_cache=True),
        lambda: dynamic_configs.get_or_create("SITE_NAME", "str", "Other"),
    ],
    ids=["no_cache", "get_or_create"],
)


def route_reads_to_the_replica(mocker):
    """Seed the setting on both databases and route reads to ``replica``, writes to ``default``."""
    for alias in ("default", "replica"):
        Config.objects.using(alias).create(name="SITE_NAME", type="str", value="Example")
    mocker.patch.object(router, "db_for_read", return_value="replica")
    mocker.patch.object(router, "db_for_write", return_value="default")


@reads_past_the_cache
@pytest.mark.django_db(databases=["default", "replica"])
def test_reads_past_the_cache_refresh_it_from_the_primary(
    read_past_the_cache, mocker, django_capture_on_commit_callbacks
):
    # With a primary/replica router, a re-read on a lagging replica could set a stale value over a writer's entry.
    route_reads_to_the_replica(mocker)
    write_from_database = mocker.patch.object(cache, "write_from_database")
    with django_capture_on_commit_callbacks(execute=True):
        read_past_the_cache()
    write_from_database.assert_called_once_with("SITE_NAME", "default", gone=cache.ABSENT)


@reads_past_the_cache
@pytest.mark.django_db(transaction=True, databases=["default", "replica"])
def test_a_read_past_the_cache_on_a_replica_never_caches_a_rolled_back_write(read_past_the_cache, mocker):
    # Review focus: transaction=True, so the replica's connection is outside the caller's transaction, as in
    # production. Waiting for the replica's commit ran the re-read at once, on the primary connection still inside
    # the uncommitted atomic(), and cached the value it then rolled back.
    route_reads_to_the_replica(mocker)
    try:
        with transaction.atomic(using="default"):
            dynamic_configs.update("SITE_NAME", "Uncommitted")
            read_past_the_cache()
            raise RuntimeError("roll back")
    except RuntimeError:
        pass
    assert Config.objects.using("default").get(name="SITE_NAME").value == "Example"
    assert dynamic_configs.get("SITE_NAME") == "Example"


def test_update_opens_its_transaction_on_the_routers_write_alias(mocker):
    make("MAX_RETRIES", "int", "3")
    mocker.patch("dynamic_configs.api.router.db_for_write", return_value="default")
    atomic = mocker.spy(transaction, "atomic")
    dynamic_configs.update("MAX_RETRIES", 5)
    atomic.assert_any_call(using="default")


@pytest.mark.parametrize(
    "call",
    [
        lambda name: dynamic_configs.update(name, 1),
        lambda name: dynamic_configs.delete(name),
        lambda name: dynamic_configs.get_or_create(name, "int", 1),
    ],
    ids=["update", "delete", "get_or_create"],
)
def test_update_delete_and_get_or_create_check_the_name_first(call, django_assert_num_queries):
    with django_assert_num_queries(0), pytest.raises(ConfigValueError, match="Invalid config name 'site name'"):
        call("site name")
