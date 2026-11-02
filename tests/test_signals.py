import pytest
from django.db import transaction

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
