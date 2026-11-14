"""Whole-number inputs (admin.js): a decimal typed into one is trimmed to its whole part, in a real browser."""

import json

import pytest
from playwright.sync_api import expect

from dynamic_configs.models import Config


@pytest.fixture
def retries(admin_page):
    """Open the change page of an int config, and return the page."""
    Config.objects.create(name="RETRIES", type="int", value="3")
    admin_page.goto("/admin/dynamic_configs/config/RETRIES/change/")
    return admin_page


def value_input(page):
    return page.locator("input[name=value]")


def save(page):
    page.get_by_role("button", name="Save", exact=True).click()


@pytest.mark.parametrize(
    ("typed", "shown"),
    [
        ("1.7", "1"),
        ("-1.7", "-1"),
        ("-0.5", "0"),
        ("1.0", "1"),
        (".5", "0"),
        ("-.5", "0"),
        # Trimmed as text: as a JavaScript number, this would round to 12345678901234567000.
        ("12345678901234567890.9", "12345678901234567890"),
        # Not a decimal: left for the server, which refuses it.
        ("1e3", "1e3"),
    ],
)
def test_a_decimal_is_trimmed_to_its_whole_part_on_leaving_the_input(retries, typed, shown):
    value_input(retries).fill(typed)
    value_input(retries).press("Tab")
    expect(value_input(retries)).to_have_value(shown)


@pytest.mark.parametrize(("key", "shown"), [("ArrowUp", "2"), ("ArrowDown", "1")])
def test_a_step_from_a_decimal_lands_on_a_whole_number(retries, key, shown):
    value_input(retries).fill("1.7")
    value_input(retries).press(key)
    expect(value_input(retries)).to_have_value(shown)


def test_a_refused_decimal_shown_again_is_trimmed_and_steps_by_whole_numbers(retries):
    # Without the script (the first page's is blocked), the server refuses the decimal and shows it again, which made
    # the browser count steps from it: up from 2 went to 2.7.
    retries.route(
        "**/dynamic_configs/admin.js",
        lambda route: route.fulfill(content_type="text/javascript", body=""),
        times=1,
    )
    retries.reload()
    value_input(retries).fill("1.7")
    save(retries)
    expect(retries.locator(".errorlist")).to_contain_text("Enter a whole number.")
    expect(value_input(retries)).to_have_value("1")
    value_input(retries).fill("2")
    value_input(retries).press("ArrowUp")
    expect(value_input(retries)).to_have_value("3")


def test_enter_saves_the_whole_part(retries):
    value_input(retries).fill("7.9")
    value_input(retries).press("Enter")
    expect(retries.locator(".messagelist")).to_contain_text("was changed successfully")
    assert Config.objects.get(name="RETRIES").value == "7"


@pytest.mark.parametrize("add", ["Enter", "button"])
def test_a_list_item_is_added_as_its_whole_part(admin_page, add):
    Config.objects.create(name="PORTS", type="list:int", value=json.dumps(["80"]))
    admin_page.goto("/admin/dynamic_configs/config/PORTS/change/")
    item = admin_page.locator("[name=value__item]")
    item.fill("443.5")
    if add == "Enter":
        item.press("Enter")
    else:
        admin_page.get_by_role("button", name="Add", exact=True).click()
    expect(admin_page.get_by_role("listbox", name="Items").locator("option")).to_have_text(["80", "443"])
