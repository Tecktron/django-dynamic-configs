"""The admin script's time zone helpers, in a real browser.

The site's zone is America/New_York (tests/settings.py) and the browser's is Asia/Tokyo (conftest.py).
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import expect

from .conftest import BROWSER_ZONE
from .models import Event

SITE_ZONE = "America/New_York"
ADD_EVENT = "/admin/browser/event/add/"


def field(page, name):
    """Return the form row for the field ``name``."""
    return page.locator(f".field-{name}")


def assert_shows_now_in(time_input, zone):
    """Assert ``time_input`` holds the current time in ``zone``, give or take a couple of minutes."""
    shown = datetime.strptime(time_input.input_value(), "%H:%M:%S").time()
    now = datetime.now(ZoneInfo(zone))
    gap = abs(datetime.combine(now.date(), shown) - now.replace(tzinfo=None))
    assert min(gap, timedelta(days=1) - gap) < timedelta(minutes=2)


def test_an_empty_datetime_starts_on_the_browsers_zone(admin_page):
    admin_page.goto(ADD_EVENT)
    expect(admin_page.locator("select[name=starts_at_2]")).to_have_value(BROWSER_ZONE)


def test_a_stored_datetime_keeps_the_zone_it_is_shown_in(admin_page):
    # Moving it to the browser's zone would change the instant if the admin saved without looking.
    event = Event.objects.create(name="Launch", starts_at=datetime(2026, 11, 2, 22, tzinfo=dt_timezone.utc))
    admin_page.goto(f"/admin/browser/event/{event.pk}/change/")
    expect(admin_page.locator("select[name=starts_at_2]")).to_have_value(SITE_ZONE)
    expect(admin_page.locator("select[name=ends_at_2]")).to_have_value(BROWSER_ZONE)


def test_each_datetimes_note_follows_its_own_zone(admin_page):
    admin_page.goto(ADD_EVENT)
    admin_page.locator("select[name=starts_at_2]").select_option(SITE_ZONE)
    expect(field(admin_page, "starts_at").locator(".timezonewarning")).to_contain_text(SITE_ZONE)
    # Still on the browser's zone, so no note.
    expect(field(admin_page, "ends_at").locator(".timezonewarning")).to_have_count(0)


def test_now_gives_the_time_in_each_datetimes_own_zone(admin_page):
    admin_page.goto(ADD_EVENT)
    admin_page.locator("select[name=starts_at_2]").select_option("UTC")
    field(admin_page, "starts_at").get_by_role("button", name="Now").click()
    field(admin_page, "ends_at").get_by_role("button", name="Now").click()
    assert_shows_now_in(admin_page.locator("[name=starts_at_1]"), "UTC")
    assert_shows_now_in(admin_page.locator("[name=ends_at_1]"), BROWSER_ZONE)


def test_the_zone_links_pick_the_sites_zone_and_the_browsers(admin_page):
    admin_page.goto(ADD_EVENT)
    starts_at = field(admin_page, "starts_at")
    zone = admin_page.locator("select[name=starts_at_2]")
    starts_at.get_by_role("link", name="Server zone").click()
    expect(zone).to_have_value(SITE_ZONE)
    # The link changes the select as choosing it would, so the note follows.
    expect(starts_at.locator(".timezonewarning")).to_contain_text(SITE_ZONE)
    starts_at.get_by_role("link", name="My zone").click()
    expect(zone).to_have_value(BROWSER_ZONE)
    expect(starts_at.locator(".timezonewarning")).to_have_count(0)


def test_the_server_zone_link_is_left_out_when_the_select_doesnt_offer_that_zone(admin_page, settings):
    settings.TIME_ZONE = "Factory"
    admin_page.goto(ADD_EVENT)
    starts_at = field(admin_page, "starts_at")
    expect(starts_at.get_by_role("link", name="Server zone")).to_have_count(0)
    expect(starts_at.get_by_role("link", name="My zone")).to_have_count(1)


def test_an_added_inline_row_starts_on_the_browsers_zone_with_its_links(admin_page):
    admin_page.goto(ADD_EVENT)
    admin_page.locator(".add-row a").click()
    row = admin_page.locator("#session_set-0")
    expect(row.locator("select[name='session_set-0-starts_at_2']")).to_have_value(BROWSER_ZONE)
    # Once: the row is copied from a template row that already has them.
    expect(row.get_by_role("link", name="Server zone")).to_have_count(1)
    row.get_by_role("link", name="Server zone").click()
    expect(row.locator("select[name='session_set-0-starts_at_2']")).to_have_value(SITE_ZONE)
