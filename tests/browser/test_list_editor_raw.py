"""The list editor's raw mode, and the list field without JavaScript, in a real browser."""

import json

from playwright.sync_api import expect

from dynamic_configs.models import Config

CHANGE = "/admin/dynamic_configs/config/{}/change/"


def open_config(page, name, type_key, texts):
    Config.objects.create(name=name, type=type_key, value=json.dumps(texts))
    page.goto(CHANGE.format(name))


def stored(name):
    return json.loads(Config.objects.get(name=name).value)


def options(page):
    return page.get_by_role("listbox", name="Items").locator("option")


# The element's box as the page measures it: Playwright's WebKit gives a list's options no box of their own.
def box(locator):
    return locator.evaluate("element => element.getBoundingClientRect().toJSON()")


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def raw_text(page):
    return page.locator("textarea[name=value]")


def raw_mode(page):
    page.get_by_role("button", name="Raw mode").click()


def save(page):
    page.get_by_role("button", name="Save", exact=True).click()


def test_raw_mode_shows_the_list_one_item_per_line_and_apply_checks_every_line(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["80", "443"])
    raw_mode(admin_page)
    expect(raw_text(admin_page)).to_have_value("80\n443")
    raw_text(admin_page).fill("80\nhttp\n8080")
    button(admin_page, "Apply").click()
    expect(admin_page.locator(".dynamic-configs-list-raw-errors li")).to_have_text(
        ["Line 2: Enter a whole number, such as 42."]
    )
    raw_text(admin_page).fill("80\n 8443\n8080")
    button(admin_page, "Apply").click()
    expect(options(admin_page)).to_have_text(["80", "8443", "8080"])


def test_each_mode_shows_only_its_own_help(admin_page):
    open_config(admin_page, "FLAGS", "list:bool", ["true"])
    item_help = admin_page.get_by_text("Checked means true.")
    raw_help = admin_page.get_by_text("One item per line. Each item: true or false")
    expect(item_help).to_be_visible()
    expect(raw_help).to_be_hidden()
    raw_mode(admin_page)
    expect(item_help).to_be_hidden()
    expect(raw_help).to_be_visible()


def test_cancel_leaves_the_list_as_it_was(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["80"])
    raw_mode(admin_page)
    raw_text(admin_page).fill("1\n2")
    button(admin_page, "Cancel").click()
    expect(options(admin_page)).to_have_text(["80"])


def test_raw_mode_refuses_a_list_with_a_line_break_item(admin_page):
    open_config(admin_page, "SIGNATURES", "list:text", ["Thanks", "Regards,\nThe team"])
    raw_mode(admin_page)
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text(
        "Item 2 contains a line break, so the list can't be shown one item per line. Edit it in the item editor."
    )
    expect(options(admin_page)).to_have_count(2)


def test_blank_lines_are_empty_items_and_a_note_names_them(admin_page):
    open_config(admin_page, "TAGS", "list:str", ["a"])
    raw_mode(admin_page)
    # Line 3 is spaces, kept as they are (STRIP_STRINGS is None); the trailing line break makes line 5.
    raw_text(admin_page).fill("a\n\n   \nb\n")
    button(admin_page, "Apply").click()
    expect(options(admin_page)).to_have_count(5)
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text(
        "Lines 2, 3 and 5 were blank, so they were added as blank items."
    )
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("TAGS") == ["a", "", "   ", "b", ""]


def test_one_blank_line_is_named_alone(admin_page):
    open_config(admin_page, "TAGS", "list:str", ["a"])
    raw_mode(admin_page)
    raw_text(admin_page).fill("a\n")
    button(admin_page, "Apply").click()
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text(
        "Line 2 was blank, so it was added as a blank item."
    )


def test_an_empty_raw_textarea_is_an_empty_list_with_no_note(admin_page):
    open_config(admin_page, "TAGS", "list:str", ["a"])
    raw_mode(admin_page)
    raw_text(admin_page).fill("")
    button(admin_page, "Apply").click()
    expect(options(admin_page)).to_have_count(0)
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text("")


def test_raw_mode_refuses_a_list_of_one_empty_item(admin_page):
    open_config(admin_page, "TAGS", "list:str", [""])
    raw_mode(admin_page)
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text(
        "The list is one empty item, which raw mode would show as no items. Edit it in the item editor."
    )
    expect(options(admin_page)).to_have_count(1)


def test_raw_text_is_editable_once_the_line_break_item_is_removed(admin_page):
    open_config(admin_page, "SIGNATURES", "list:text", ["Thanks", "Regards,\nThe team"])
    # A real click on the item's row.
    admin_page.get_by_role("listbox", name="Items").scroll_into_view_if_needed()
    row = box(options(admin_page).nth(1))
    admin_page.mouse.click(row["x"] + row["width"] / 2, row["y"] + row["height"] / 2)
    expect(button(admin_page, "Update")).to_be_visible()
    button(admin_page, "Remove").click()
    expect(options(admin_page)).to_have_count(1)
    raw_mode(admin_page)
    expect(raw_text(admin_page)).to_be_editable()
    expect(raw_text(admin_page)).to_have_value("Thanks")


def test_raw_mode_will_not_open_over_an_unfinished_item(admin_page):
    admin_page.goto("/admin/dynamic_configs/config/add/?type=list:str")
    admin_page.locator("[name=value__item]").fill("x")
    raw_mode(admin_page)
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text(
        "You have an unsaved change to an item: click Update or Clear."
    )
    expect(raw_text(admin_page)).to_be_hidden()
    expect(admin_page.locator("[name=value__item]")).to_have_value("x")


def test_an_old_note_is_gone_after_raw_mode_is_opened_and_cancelled(admin_page):
    open_config(admin_page, "TAGS", "list:str", ["a"])
    raw_mode(admin_page)
    raw_text(admin_page).fill("a\n")
    button(admin_page, "Apply").click()
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text(
        "Line 2 was blank, so it was added as a blank item."
    )
    raw_mode(admin_page)
    button(admin_page, "Cancel").click()
    expect(admin_page.locator(".dynamic-configs-list-message")).to_have_text("")


def test_saving_with_raw_mode_open_saves_the_raw_text(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["80"])
    raw_mode(admin_page)
    raw_text(admin_page).fill("1\n2")
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PORTS") == ["1", "2"]


def test_a_failed_raw_save_comes_back_in_raw_mode(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["80"])
    raw_mode(admin_page)
    raw_text(admin_page).fill("1\nx")
    save(admin_page)
    # Django's own error list for the field (the editor's raw errors list has the errorlist class too).
    expect(admin_page.locator(".errorlist:not(.dynamic-configs-list-raw-errors)")).to_contain_text(
        "Line 2: Enter a whole number"
    )
    # The text isn't a list yet, so the page opens in raw mode, with no list to cancel back to.
    expect(raw_text(admin_page)).to_have_value("1\nx")
    expect(button(admin_page, "Cancel")).to_be_hidden()
    raw_text(admin_page).fill("1\n2")
    button(admin_page, "Apply").click()
    expect(options(admin_page)).to_have_text(["1", "2"])


def test_without_javascript_the_list_is_the_raw_textarea(browser, live_server, admin_cookie):
    Config.objects.create(name="PORTS", type="list:int", value='["80"]')
    context = browser.new_context(java_script_enabled=False, base_url=live_server.url)
    context.add_cookies([admin_cookie])
    page = context.new_page()
    page.goto(CHANGE.format("PORTS"))
    expect(raw_text(page)).to_have_value("80")
    expect(page.locator("[name=value__item]")).to_be_hidden()
    raw_text(page).fill("80\n443")
    save(page)
    expect(page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PORTS") == ["80", "443"]
    context.close()


def test_without_javascript_a_line_break_item_is_read_only_and_kept(browser, live_server, admin_cookie):
    texts = ["Regards,\nThe team"]
    Config.objects.create(name="SIGNATURES", type="list:text", value=json.dumps(texts))
    context = browser.new_context(java_script_enabled=False, base_url=live_server.url)
    context.add_cookies([admin_cookie])
    page = context.new_page()
    page.goto(CHANGE.format("SIGNATURES"))
    expect(raw_text(page)).to_have_attribute("readonly", "")
    expect(page.locator(".dynamic-configs-list-locked")).to_contain_text("editing it needs JavaScript")
    save(page)
    expect(page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("SIGNATURES") == texts
    context.close()
