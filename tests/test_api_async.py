import asyncio

import pytest

import dynamic_configs
from dynamic_configs import _overrides


@pytest.mark.django_db(transaction=True)
def test_the_async_api_matches_the_sync_api():
    # transaction=True: sync_to_async runs the ORM in another thread, which can't see an uncommitted test transaction.
    async def scenario():
        created = await dynamic_configs.aget_or_create("MAX_RETRIES", "int", 3, description="Retries.")
        await dynamic_configs.aupdate("MAX_RETRIES", 4)
        value = await dynamic_configs.aget("MAX_RETRIES", no_cache=True)
        deleted = await dynamic_configs.adelete("MAX_RETRIES")
        missing = await dynamic_configs.aget("MAX_RETRIES", default=None)
        return created, value, deleted, missing

    assert asyncio.run(scenario()) == ((3, True), 4, True, None)


def test_aget_sees_overrides_from_the_calling_context():
    token = _overrides.push({"SITE_NAME": "Overridden"})
    try:
        assert asyncio.run(dynamic_configs.aget("SITE_NAME")) == "Overridden"
    finally:
        _overrides.pop(token)
