"""Fixtures for the browser tests: a live server, a logged-in admin in Chromium, and a check for console errors.

These tests run the admin's scripts in a real browser with Playwright. The matrix tox environments skip this directory;
the ``browser`` environment runs it.
"""

import os
from pathlib import Path

import pytest
from django.test import Client

# Look for the browser inside the Playwright package (installed with PLAYWRIGHT_BROWSERS_PATH=0), so it lives in the
# virtualenv rather than a cache in the home directory.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

# The browser's own zone: far from the site's TIME_ZONE (America/New_York), so a test can tell the two apart.
BROWSER_ZONE = "Asia/Tokyo"


@pytest.fixture
def browser_context_args(browser_context_args, live_server):
    """Point pages at the live server, and fix the browser's time zone so the tests don't depend on the machine's."""
    return {**browser_context_args, "base_url": live_server.url, "timezone_id": BROWSER_ZONE}


def pytest_collection_modifyitems(items):
    """Run the browser tests after all the others (see ``_django_from_playwright``)."""
    here = Path(__file__).parent
    items.sort(key=lambda item: item.path.is_relative_to(here))


@pytest.fixture(scope="session", autouse=True)
def _django_from_playwright():
    """Allow Django's database calls from the first browser test to the end of the run.

    Playwright starts an event loop on the test thread that runs until the session ends, so Django would refuse database
    calls as if they came from async code. The browser tests run last, so every other test keeps Django's check.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
        yield


@pytest.fixture
def admin_page(page, live_server, django_user_model):
    """Return a Playwright page logged in to the admin, failing the test on any console error."""
    user = django_user_model.objects.create_superuser("admin", "admin@example.com", "password")
    client = Client()
    client.force_login(user)
    page.context.add_cookies(
        [{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": live_server.url}]
    )
    errors = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    assert errors == []
