import json
import logging

import pytest

from dynamic_configs import cache


def test_keys_are_versioned_and_namespaced():
    assert cache.cache_key("SITE_NAME") == "dynamic_configs:v1:SITE_NAME"


def test_entries_round_trip():
    cache.write("SITE_NAME", ("str", "Example"))
    assert cache.read("SITE_NAME") == ("str", "Example")


def test_absent_settings_are_cached_as_a_marker():
    cache.write("MISSING", cache.ABSENT)
    assert cache.read("MISSING") is cache.ABSENT


def test_nothing_cached_reads_as_not_cached():
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


@pytest.mark.parametrize("text", ["Example", None])
def test_entries_from_a_cache_that_stores_json_read_as_hits(text):
    # Review: caches that serialize to JSON or msgpack (django-redis's JSON serializer, say) give lists back, which
    # read as misses, so every get() went to the database and the fill (an add) never replaced the entry.
    cache.get_cache().set(cache.cache_key("SITE_NAME"), json.loads(json.dumps(("str", text))))
    assert cache.read("SITE_NAME") == ("str", text)


def test_unexpected_cached_values_read_as_not_cached():
    cache.get_cache().set(cache.cache_key("SITE_NAME"), "garbage")
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


def test_delete_removes_the_entry():
    cache.write("SITE_NAME", ("str", "Example"))
    cache.delete("SITE_NAME")
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


def test_cache_none_disables_caching(settings):
    settings.DYNAMIC_CONFIGS = {"CACHE": None}
    assert cache.get_cache() is None
    cache.write("SITE_NAME", ("str", "Example"))
    cache.delete("SITE_NAME")
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


def test_dummy_cache_counts_as_disabled(settings):
    settings.DYNAMIC_CONFIGS = {"CACHE": "dummy"}
    assert cache.get_cache() is None


def test_an_unconfigured_alias_disables_caching_with_a_warning(settings, caplog):
    settings.DYNAMIC_CONFIGS = {"CACHE": "missing"}
    assert cache.get_cache() is None
    assert "Cache alias 'missing' isn't configured" in caplog.text


def test_the_timeout_comes_from_settings(settings):
    settings.DYNAMIC_CONFIGS = {"TIMEOUT": 0}
    cache.write("SITE_NAME", ("str", "Example"))
    # A timeout of 0 expires the entry immediately.
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


def test_cache_errors_are_logged_and_never_raised(settings, caplog):
    settings.DYNAMIC_CONFIGS = {"CACHE": "failing"}
    assert cache.read("SITE_NAME") is cache.NOT_CACHED
    cache.write("SITE_NAME", ("str", "Example"))
    cache.delete("SITE_NAME")
    messages = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert messages == [
        "Cache read failed for config 'SITE_NAME'; reading from the database",
        "Cache write failed for config 'SITE_NAME'; any old entry expires after the cache timeout",
        "Cache delete failed for config 'SITE_NAME'; any old entry expires after the cache timeout",
    ]
    assert all(record.config_name == "SITE_NAME" for record in caplog.records)


def test_hits_and_misses_are_logged_at_debug(caplog):
    caplog.set_level(logging.DEBUG, logger="dynamic_configs")
    cache.read("SITE_NAME")
    cache.write("SITE_NAME", ("str", "Example"))
    cache.read("SITE_NAME")
    cache.write("GONE", cache.ABSENT)
    cache.read("GONE")
    assert [record.getMessage() for record in caplog.records] == [
        "Cache miss for config 'SITE_NAME'",
        "Cached config 'SITE_NAME'",
        "Cache hit for config 'SITE_NAME'",
        "Cached config 'GONE'",
        "Cache hit for config 'GONE': it doesn't exist",
    ]


def test_markers_name_themselves_in_repr():
    assert repr(cache.ABSENT) == "ABSENT"
    assert repr(cache.NOT_CACHED) == "NOT_CACHED"


def test_a_fill_never_replaces_an_existing_entry():
    # Review finding: a slow reader's fill could overwrite the newer entry a writer cached after committing.
    cache.write("SITE_NAME", ("str", "New"))
    cache.write("SITE_NAME", ("str", "Old"), overwrite=False)
    assert cache.read("SITE_NAME") == ("str", "New")
