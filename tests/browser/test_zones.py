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
    """Return the form row for the field ``name`` (not the inline's hidden template row, which has the class too)."""
    return page.locator(f".field-{name}").filter(visible=True)


def click_now(page, name):
    # By its text, among the shortcuts beside the input (the clock popup has a Now too): Django 6 gives the link a
    # button role, 5.2 doesn't.
    field(page, name).locator(".datetimeshortcuts").get_by_text("Now", exact=True).click()


def expect_notes_for(page, name, zone):
    """Expect the notes under the field ``name`` to be for ``zone``.

    Django 6 names the zone in its note and shows one per datetime; Django 5.2 shows one per input and doesn't name the
    zone. Both say how far ahead the browser is.
    """
    now = datetime.now(dt_timezone.utc)
    hours = (now.astimezone(ZoneInfo(BROWSER_ZONE)).utcoffset() - now.astimezone(ZoneInfo(zone)).utcoffset()) // (
        timedelta(hours=1)
    )
    notes = field(page, name).locator(".timezonewarning")
    expect(notes.first).to_contain_text(f"You are {hours} hours ahead")
    assert all(f"You are {hours} hours ahead" in text for text in notes.all_inner_texts())


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
    expect_notes_for(admin_page, "starts_at", SITE_ZONE)
    # Still on the browser's zone, so no note.
    expect(field(admin_page, "ends_at").locator(".timezonewarning")).to_have_count(0)


def test_now_gives_the_time_in_each_datetimes_own_zone(admin_page):
    admin_page.goto(ADD_EVENT)
    admin_page.locator("select[name=starts_at_2]").select_option("UTC")
    click_now(admin_page, "starts_at")
    click_now(admin_page, "ends_at")
    assert_shows_now_in(admin_page.locator("[name=starts_at_1]"), "UTC")
    assert_shows_now_in(admin_page.locator("[name=ends_at_1]"), BROWSER_ZONE)


def test_the_zone_links_pick_the_sites_zone_and_the_browsers(admin_page):
    admin_page.goto(ADD_EVENT)
    starts_at = field(admin_page, "starts_at")
    zone = admin_page.locator("select[name=starts_at_2]")
    starts_at.get_by_role("link", name="Server zone").click()
    expect(zone).to_have_value(SITE_ZONE)
    # The link changes the select as choosing it would, so the note follows.
    expect_notes_for(admin_page, "starts_at", SITE_ZONE)
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
