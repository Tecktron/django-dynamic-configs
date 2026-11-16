import logging
import threading

import pytest
from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, transaction

import dynamic_configs
from dynamic_configs import cache
from dynamic_configs.models import Config

pytestmark = pytest.mark.django_db


def test_saving_clears_the_entry_at_once_and_caches_after_commit(django_capture_on_commit_callbacks):
    cache.write("SITE_NAME", ("str", "Old"))
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        Config.objects.create(name="SITE_NAME", type="str", value="New")
        assert cache.read("SITE_NAME") is cache.NOT_CACHED
    assert len(callbacks) == 1
    callbacks[0]()
    assert cache.read("SITE_NAME") == ("str", "New")


def test_deleting_caches_the_absent_marker_after_commit(django_capture_on_commit_callbacks):
    config = Config.objects.create(name="SITE_NAME", type="str", value="Example")
    with django_capture_on_commit_callbacks(execute=True):
        config.delete()
    assert cache.read("SITE_NAME") is cache.ABSENT


def test_queryset_delete_also_updates_the_cache(django_capture_on_commit_callbacks):
    Config.objects.create(name="SITE_NAME", type="str", value="Example")
    with django_capture_on_commit_callbacks(execute=True):
        Config.objects.filter(name="SITE_NAME").delete()
    assert cache.read("SITE_NAME") is cache.ABSENT


def test_a_rolled_back_save_never_reaches_the_cache(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        try:
            with transaction.atomic():
                Config.objects.create(name="SITE_NAME", type="str", value="Example")
                raise RuntimeError("roll back")
        except RuntimeError:
            pass
    assert callbacks == []
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


def test_saving_only_the_description_caches_the_database_value(django_capture_on_commit_callbacks):
    # F10: a stale copy saving only its description cached its own, older value.
    Config.objects.create(name="SITE_NAME", type="str", value="Old")
    stale = Config.objects.get(name="SITE_NAME")
    with django_capture_on_commit_callbacks(execute=True):
        dynamic_configs.update("SITE_NAME", "New")
    stale.description = "The site's name."
    with django_capture_on_commit_callbacks(execute=True):
        stale.save(update_fields=["description"])
    assert cache.read("SITE_NAME") == ("str", "New")


def test_saving_a_row_with_a_python_value_caches_the_stored_text(
    caplog, django_assert_num_queries, django_capture_on_commit_callbacks
):
    # F18: the int 5 was cached while the database held "5", so cached reads failed.
    row = Config.objects.create(name="MAX_RETRIES", type="int", value="1")
    row.value = 5
    with django_capture_on_commit_callbacks(execute=True):
        row.save()
    with django_assert_num_queries(0):
        assert dynamic_configs.get("MAX_RETRIES") == 5
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


def test_a_save_and_a_delete_in_one_transaction_cache_no_value(mocker, django_capture_on_commit_callbacks):
    # Review focus: the save's on-commit re-read finds no row, so it caches nothing; the delete caches the marker.
    backend_set = mocker.spy(cache.get_cache(), "set")
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        config = Config.objects.create(name="SITE_NAME", type="str", value="Example")
        config.delete()
    assert cache.read("SITE_NAME") is cache.ABSENT
    assert not any(isinstance(call.args[1], (tuple, list)) for call in backend_set.call_args_list)


def test_deleting_then_recreating_in_one_transaction_caches_the_new_row(django_capture_on_commit_callbacks):
    Config.objects.create(name="SITE_NAME", type="str", value="Old")
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        Config.objects.filter(name="SITE_NAME").delete()
        Config.objects.create(name="SITE_NAME", type="str", value="New")
    assert cache.read("SITE_NAME") == ("str", "New")


def delete_from_another_connection(name):
    """Delete the row with plain SQL on a second connection (a thread has its own), sending no signals."""

    def run():
        try:
            with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
                cursor.execute("DELETE FROM dynamic_configs_config WHERE name = %s", [name])
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()


@pytest.mark.django_db(transaction=True)
def test_a_row_deleted_before_the_commit_callback_is_not_cached(mocker):
    # Review focus: transaction=True, so the save really commits, and a second connection (on SQLite, the shared
    # in-memory test database; on PostgreSQL, a second session) deletes the row before the save's callback runs.
    real_on_commit = transaction.on_commit

    def on_commit(func, using=None, robust=False):
        def delete_first():
            delete_from_another_connection("SITE_NAME")
            func()

        real_on_commit(delete_first, using=using, robust=robust)

    mocker.patch.object(transaction, "on_commit", on_commit)
    with transaction.atomic():
        Config.objects.create(name="SITE_NAME", type="str", value="Example")
    assert not Config.objects.filter(name="SITE_NAME").exists()
    assert cache.read("SITE_NAME") is cache.NOT_CACHED


def test_a_database_error_in_the_commit_callback_is_logged_and_drops_the_entry(
    mocker, caplog, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        Config.objects.create(name="SITE_NAME", type="str", value="Example")
    # A slow reader's fill landed between the save and its callback.
    cache.write("SITE_NAME", ("str", "Old"))
    mocker.patch("django.db.models.query.QuerySet.first", side_effect=DatabaseError("down"))
    callbacks[0]()
    assert cache.read("SITE_NAME") is cache.NOT_CACHED
    assert [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING] == [
        "Database read failed for config 'SITE_NAME' after a commit; dropped its cache entry"
    ]
