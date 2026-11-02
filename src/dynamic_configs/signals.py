"""Keep cache entries in step with saves and deletes.

The entry is removed at once, so reads inside the same transaction go to the database, and replaced only when the
transaction commits, so a rolled-back save never reaches the cache. Admin saves, the API and ``QuerySet.delete()`` all
send these signals; ``QuerySet.update()``, ``bulk_create()`` and ``bulk_update()`` don't.
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
    """Drop the cached entry now and cache the saved one when the transaction commits."""
    cache.delete(instance.name)
    transaction.on_commit(partial(cache.write, instance.name, (instance.type, instance.value)), using=using)


@receiver(post_delete, sender=Config, dispatch_uid="dynamic_configs.config_deleted")
def config_deleted(sender: type[Config], instance: Config, using: str, **kwargs: Any) -> None:
    """Drop the cached entry now and cache the "doesn't exist" marker when the transaction commits."""
    cache.delete(instance.name)
    transaction.on_commit(partial(cache.write, instance.name, cache.ABSENT), using=using)
