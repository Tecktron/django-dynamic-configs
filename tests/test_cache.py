import json
import logging
import warnings

import pytest
from django.core.cache import CacheKeyWarning

from dynamic_configs import cache


def test_keys_are_versioned_and_namespaced():
    assert cache.cache_key("SITE_NAME", cache.get_cache()) == "dynamic_configs:v1:SITE_NAME"


def test_the_longest_name_whose_key_fits_keeps_its_plain_key():
    # Django's full key is KEY_PREFIX:VERSION:key, ":1:" by default: 3 + 19 + 228 = 250.
    backend = cache.get_cache()
    assert cache.cache_key("A" * 228, backend) == "dynamic_configs:v1:" + "A" * 228


def test_a_longer_name_gets_a_hashed_key_that_fits():
    backend = cache.get_cache()
    key = cache.cache_key("A" * 229, backend)
    assert key.startswith("dynamic_configs:v1:AAA")
    assert "#" in key
    assert len(backend.make_key(key)) <= cache.MAX_KEY_LENGTH


def test_long_names_with_the_same_start_get_different_keys():
    backend = cache.get_cache()
    assert cache.cache_key("A" * 254 + "B", backend) != cache.cache_key("A" * 254 + "C", backend)


def test_a_255_character_name_round_trips_without_a_key_warning():
    name = "A" * 255
    with warnings.catch_warnings():
        warnings.simplefilter("error", CacheKeyWarning)
        cache.write(name, ("str", "Example"))
        assert cache.read(name) == ("str", "Example")
        cache.delete(name)
        assert cache.read(name) is cache.NOT_CACHED


def test_a_long_site_key_prefix_makes_shorter_names_hash(settings):
    # 150 + 3 + 19 + 100 = 272 characters plain; the hashed key fits.
    settings.CACHES = {**settings.CACHES, "default": {**settings.CACHES["default"], "KEY_PREFIX": "x" * 150}}
    backend = cache.get_cache()
    key = cache.cache_key("A" * 100, backend)
    assert "#" in key
    assert len(backend.make_key(key)) == cache.MAX_KEY_LENGTH


def test_a_site_key_prefix_too_long_for_any_key_still_works(settings):
    # Even the hash alone can't fit (200 + 3 + 19 + 1 + 64 = 287): the backend's own warning stands, and on a backend
    # that raises instead (Memcached), cache errors are already logged and fall back to the database.
    settings.CACHES = {**settings.CACHES, "default": {**settings.CACHES["default"], "KEY_PREFIX": "x" * 200}}
    with pytest.warns(CacheKeyWarning):
        cache.write("A" * 40, ("str", "Example"))
    with pytest.warns(CacheKeyWarning):
        assert cache.read("A" * 40) == ("str", "Example")


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
    cache.get_cache().set(cache.cache_key("SITE_NAME", cache.get_cache()), json.loads(json.dumps(("str", text))))
    assert cache.read("SITE_NAME") == ("str", text)


def test_unexpected_cached_values_read_as_not_cached():
    cache.get_cache().set(cache.cache_key("SITE_NAME", cache.get_cache()), "garbage")
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
