"""Keep cache entries in step with saves and deletes.

The entry is removed at once, so reads inside the same transaction go to the database. When the transaction commits,
the row is read again and what the database then holds is cached: a rolled-back save never reaches the cache, a save
of some fields never caches a stale copy's other fields, and of two writers the one whose callback runs last can't
cache an older value. Admin saves, the API and ``QuerySet.delete()`` all send these signals; ``QuerySet.update()``,
``bulk_create()``, ``bulk_update()`` and data migrations' historical models don't.
"""

from functools import partial
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from dynamic_configs import cache
from dynamic_configs.models import Config


@receiver(post_save, sender=Config, dispatch_uid="dynamic_configs.config_saved")
def config_saved(sender: type[Config], instance: Config, using: str, **kwargs: Any) -> None:
    """Drop the cached entry now and cache the row as the database holds it when the transaction commits."""
    cache.delete(instance.name)
    transaction.on_commit(partial(cache.write_from_database, instance.name, using, gone=None), using=using)


@receiver(post_delete, sender=Config, dispatch_uid="dynamic_configs.config_deleted")
def config_deleted(sender: type[Config], instance: Config, using: str, **kwargs: Any) -> None:
    """Drop the cached entry now and cache the "doesn't exist" marker when the transaction commits.

    If another transaction has created the setting again by then, its row is cached instead.
    """
    cache.delete(instance.name)
    transaction.on_commit(partial(cache.write_from_database, instance.name, using, gone=cache.ABSENT), using=using)
