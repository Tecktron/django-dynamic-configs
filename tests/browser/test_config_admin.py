"""The admin script on the config admin's own pages, in a real browser."""

import pytest
from playwright.sync_api import expect

ADD = "/admin/dynamic_configs/config/add/"

# Count the type form's submits and cancel them, so the page stays put and a submit that shouldn't happen is seen.
CATCH_SUBMITS = """select => {
    window.catchSubmit = (event) => {
        event.preventDefault();
        document.body.dataset.submits = String(Number(document.body.dataset.submits ?? 0) + 1);
    };
    select.form.addEventListener("submit", window.catchSubmit);
}"""


def type_select(page):
    return page.locator("select[name=type]")


def test_choosing_a_type_moves_on_to_the_value(admin_page):
    admin_page.goto(ADD)
    type_select(admin_page).select_option("int")
    expect(admin_page).to_have_url(f"{ADD}?type=int")
    expect(admin_page.locator("[name=value]")).to_be_visible()


def test_arrow_keys_on_the_type_select_dont_submit(admin_page):
    admin_page.goto(ADD)
    select = type_select(admin_page)
    second = select.locator("option").nth(2).get_attribute("value")
    select.evaluate(CATCH_SUBMITS)
    select.focus()
    admin_page.keyboard.press("ArrowDown")
    if select.input_value() == "":
        pytest.skip("This engine opens the select's list on ArrowDown rather than changing the choice.")
    admin_page.keyboard.press("ArrowDown")
    expect(select).to_have_value(second)
    # The change event runs as the key is handled, so a submit would have been counted by now.
    assert admin_page.evaluate("() => document.body.dataset.submits") is None
    select.evaluate('select => select.form.removeEventListener("submit", window.catchSubmit)')
    admin_page.keyboard.press("Enter")
    expect(admin_page).to_have_url(f"{ADD}?type={second}")
    expect(admin_page.locator("[name=value]")).to_be_visible()

    # A choice with the mouse after the keyboard moves on at once.
    admin_page.goto(ADD)
    type_select(admin_page).focus()
    admin_page.keyboard.press("ArrowDown")
    type_select(admin_page).dispatch_event("pointerdown")
    type_select(admin_page).select_option("int")
    expect(admin_page).to_have_url(f"{ADD}?type=int")
