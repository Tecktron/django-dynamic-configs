"""The admin script's time zone helpers, in a real browser."""

from playwright.sync_api import expect

from .conftest import BROWSER_ZONE


def test_an_empty_datetime_starts_on_the_browsers_zone(admin_page):
    admin_page.goto("/admin/browser/event/add/")
    expect(admin_page.locator("select[name=starts_at_2]")).to_have_value(BROWSER_ZONE)
