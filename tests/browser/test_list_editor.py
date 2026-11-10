"""The admin's list editor (list_editor.js), in a real browser: list mode."""

import json
from datetime import datetime
from datetime import timezone as dt_timezone

from playwright.sync_api import expect

from dynamic_configs.models import Config
from dynamic_configs.types.registry import get_registry

ADD = "/admin/dynamic_configs/config/add/?type={}"
CHANGE = "/admin/dynamic_configs/config/{}/change/"
COLOR = {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}
LETTER = {
    "type": "builtins.str",
    "serializer": "dynamic_configs.types.serializers.StrSerializer",
    "form": "tests.custom_types.LetterField",
}
LETTER_LIST = {
    "type": "builtins.list",
    "serializer": "tests.custom_types.LettersSerializer",
    "form": "tests.custom_types.LettersField",
}


def open_config(page, name, type_key, texts):
    Config.objects.create(name=name, type=type_key, value=json.dumps(texts))
    page.goto(CHANGE.format(name))


def stored(name):
    return json.loads(Config.objects.get(name=name).value)


def items(page):
    return page.get_by_role("listbox", name="Items")


def options(page):
    return items(page).locator("option")


def item_input(page):
    return page.locator("[name=value__item]")


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def message(page):
    return page.locator(".dynamic-configs-list-message")


def save(page):
    page.get_by_role("button", name="Save", exact=True).click()


def test_add_checks_each_item_with_the_server(admin_page):
    admin_page.goto(ADD.format("list:int"))
    item_input(admin_page).fill("07")
    button(admin_page, "Add").click()
    expect(options(admin_page)).to_have_text(["7"])
    expect(item_input(admin_page)).to_have_value("")
    # Chromium won't type letters into a number input; 1.5 can be typed, and isn't a whole number.
    item_input(admin_page).fill("1.5")
    button(admin_page, "Add").click()
    expect(message(admin_page)).to_have_text("Enter a whole number.")
    expect(options(admin_page)).to_have_text(["7"])


def test_an_empty_text_item_can_be_added(admin_page):
    admin_page.goto(ADD.format("list:str"))
    button(admin_page, "Add").click()
    expect(options(admin_page)).to_have_count(1)


def test_selecting_an_item_loads_it_and_update_replaces_it(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["80", "443", "8080"])
    items(admin_page).select_option(index=1)
    expect(item_input(admin_page)).to_have_value("443")
    expect(button(admin_page, "Update")).to_be_visible()
    item_input(admin_page).fill("8443")
    button(admin_page, "Update").click()
    expect(options(admin_page)).to_have_text(["80", "8443", "8080"])
    button(admin_page, "Clear").click()
    expect(button(admin_page, "Add")).to_be_visible()
    expect(item_input(admin_page)).to_have_value("")
    expect(items(admin_page)).to_have_js_property("selectedIndex", -1)


def test_remove_up_and_down_then_save(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["1", "2", "3"])
    items(admin_page).select_option(index=2)
    button(admin_page, "Up").click()
    button(admin_page, "Up").click()
    expect(options(admin_page)).to_have_text(["3", "1", "2"])
    expect(button(admin_page, "Up")).to_be_disabled()
    button(admin_page, "Down").click()
    expect(options(admin_page)).to_have_text(["1", "3", "2"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("1")
    button(admin_page, "Remove").click()
    expect(options(admin_page)).to_have_text(["3", "2"])
    expect(button(admin_page, "Remove")).to_be_disabled()
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PORTS") == ["3", "2"]


def test_sort_goes_by_value_and_flips_direction(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["10", "9", "100"])
    button(admin_page, "Sort ↑").click()
    expect(options(admin_page)).to_have_text(["9", "10", "100"])
    button(admin_page, "Sort ↓").click()
    expect(options(admin_page)).to_have_text(["100", "10", "9"])


def test_text_sorts_ignoring_case(admin_page):
    open_config(admin_page, "NAMES", "list:str", ["b", "A", "a"])
    button(admin_page, "Sort ↑").click()
    expect(options(admin_page)).to_have_text(["A", "a", "b"])


def test_sets_have_no_order_buttons_and_refuse_repeats(admin_page):
    open_config(admin_page, "CODES", "set:int", ["1"])
    for name in ("Up", "Down", "Sort ↑"):
        expect(button(admin_page, name)).to_have_count(0)
    item_input(admin_page).fill("01")
    button(admin_page, "Add").click()
    expect(message(admin_page)).to_have_text("That's already in the set.")


def test_types_that_cant_be_sorted_have_no_sort(admin_page, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"color": COLOR}}
    open_config(admin_page, "COLORS", "list:color", ["#000000", "#ffffff"])
    expect(button(admin_page, "Sort ↑")).to_have_count(0)
    expect(button(admin_page, "Up")).to_have_count(1)


def test_a_datetime_item_loads_into_its_date_time_and_zone(admin_page):
    datetimes = get_registry().get("datetime")
    text = datetimes.to_text(datetime(2026, 11, 2, 22, tzinfo=dt_timezone.utc))
    open_config(admin_page, "LAUNCHES", "list:datetime", [text])
    items(admin_page).select_option(index=0)
    expect(admin_page.locator("[name=value__item_0]")).to_have_value("2026-11-02")
    expect(admin_page.locator("[name=value__item_1]")).to_have_value("17:00:00")
    expect(admin_page.locator("[name=value__item_2]")).to_have_value("America/New_York")
    admin_page.locator("[name=value__item_1]").fill("18:00:00")
    button(admin_page, "Update").click()
    expect(options(admin_page)).not_to_have_text([text])
    assert datetimes.from_text(options(admin_page).first.text_content()) == datetime(
        2026, 11, 2, 23, tzinfo=dt_timezone.utc
    )


def test_saving_keeps_items_exactly(admin_page):
    texts = ["  INV-", "", "PO-"]
    open_config(admin_page, "PREFIXES", "list:str", texts)
    expect(options(admin_page)).to_have_count(3)
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PREFIXES") == texts


def test_a_multi_line_text_item_survives_a_save(admin_page):
    texts = ["Regards,\nThe team", "Thanks"]
    open_config(admin_page, "SIGNATURES", "list:text", texts)
    expect(options(admin_page)).to_have_count(2)
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("SIGNATURES") == texts


def test_save_is_stopped_while_the_editor_holds_an_unfinished_item(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["80"])
    item_input(admin_page).fill("443")
    save(admin_page)
    expect(message(admin_page)).to_have_text("You have an unsaved change to an item: click Update or Clear.")
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("80")
    item_input(admin_page).fill("81")
    save(admin_page)
    expect(message(admin_page)).to_have_text("You have an unsaved change to an item: click Update or Clear.")
    button(admin_page, "Clear").click()
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PORTS") == ["80"]


def test_enter_in_the_item_editor_adds_the_item(admin_page):
    admin_page.goto(ADD.format("list:int"))
    item_input(admin_page).fill("7")
    item_input(admin_page).press("Enter")
    expect(options(admin_page)).to_have_text(["7"])
    # The page wasn't submitted: the name is still waiting to be filled in, with no error.
    expect(admin_page.locator("[name=name]")).to_be_visible()
    expect(admin_page.locator(".errornote")).to_have_count(0)


def test_an_unreachable_check_url_changes_nothing(admin_page, console_errors):
    admin_page.goto(ADD.format("list:int"))
    admin_page.route("**/list-item/**", lambda route: route.fulfill(status=500))
    item_input(admin_page).fill("7")
    button(admin_page, "Add").click()
    expect(message(admin_page)).to_have_text("Couldn't check the item; try again.")
    expect(options(admin_page)).to_have_count(0)
    expect(button(admin_page, "Add")).to_be_enabled()
    # The browser logs the failed request; that error is expected.
    console_errors.clear()


def test_an_expired_session_changes_nothing(admin_page):
    # The check URL sends the browser to the login page, which answers 200 with HTML rather than JSON.
    admin_page.goto(ADD.format("list:int"))
    admin_page.context.clear_cookies(name="sessionid")
    item_input(admin_page).fill("7")
    button(admin_page, "Add").click()
    expect(message(admin_page)).to_have_text("Couldn't check the item; try again.")
    expect(options(admin_page)).to_have_count(0)
    expect(item_input(admin_page)).to_have_value("7")
    expect(button(admin_page, "Add")).to_be_enabled()


def test_the_buttons_wait_for_the_servers_answer(admin_page):
    # Review focus: a second click while the first is pending must not add the item twice.
    held = []
    admin_page.goto(ADD.format("list:int"))
    admin_page.route("**/list-item/**", lambda route: held.append(route))
    item_input(admin_page).fill("7")
    button(admin_page, "Add").click()
    expect(button(admin_page, "Add")).to_be_disabled()
    for _ in range(250):
        if held:
            break
        admin_page.wait_for_timeout(20)
    assert held, "the Add request never reached the check URL"
    held[0].continue_()
    expect(options(admin_page)).to_have_text(["7"])
    expect(button(admin_page, "Add")).to_be_enabled()


def test_item_text_is_shown_as_text(admin_page):
    # Review focus: markup in an item stays text.
    open_config(admin_page, "SNIPPETS", "list:str", ["<img src=x onerror=alert(1)>"])
    expect(options(admin_page)).to_have_text(["<img src=x onerror=alert(1)>"])
    expect(admin_page.locator(".dynamic-configs-list img")).to_have_count(0)


def test_the_list_shows_several_items_at_once(admin_page):
    # The admin's stylesheet gives every select one row's height (only multi-selects get theirs back); the list
    # keeps the rows its size asks for.
    open_config(admin_page, "PORTS", "list:int", ["80", "443", "8080"])
    expect(options(admin_page)).to_have_count(3)
    row = options(admin_page).first.bounding_box()
    assert items(admin_page).bounding_box()["height"] >= 4 * row["height"]


def test_an_unreadable_item_can_be_selected_and_removed(admin_page):
    # Review focus: a hand-edited row.
    open_config(admin_page, "PORTS", "list:int", ["1", "x"])
    items(admin_page).select_option(index=1)
    expect(message(admin_page)).to_have_text("Enter a whole number, such as 42.")
    button(admin_page, "Remove").click()
    expect(options(admin_page)).to_have_text(["1"])


def letter(page, value):
    return page.locator(f"input[name=value__item][value={value}]")


def expect_letters_checked(page, chosen):
    for value in "abc":
        if value in chosen:
            expect(letter(page, value)).to_be_checked()
        else:
            expect(letter(page, value)).not_to_be_checked()


def test_radio_buttons_add_and_load_the_chosen_value(admin_page, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"letter": LETTER}}
    open_config(admin_page, "GRADES", "list:letter", ["a"])
    letter(admin_page, "b").check()
    button(admin_page, "Add").click()
    expect(options(admin_page)).to_have_text(["a", "b"])
    expect_letters_checked(admin_page, "")
    items(admin_page).select_option(index=1)
    expect_letters_checked(admin_page, "b")
    items(admin_page).select_option(index=0)
    expect_letters_checked(admin_page, "a")
    # Loading checked a button; it didn't rewrite the buttons' own values.
    expect(item_input(admin_page)).to_have_count(3)
    # The loaded item is no unfinished change.
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("GRADES") == ["a", "b"]


def test_checkboxes_sharing_a_name_add_and_load_every_chosen_value(admin_page, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"letters": LETTER_LIST}}
    open_config(admin_page, "PAIRS", "list:letters", ["b"])
    letter(admin_page, "a").check()
    letter(admin_page, "c").check()
    button(admin_page, "Add").click()
    expect(options(admin_page)).to_have_text(["b", "a,c"])
    expect_letters_checked(admin_page, "")
    items(admin_page).select_option(index=1)
    expect_letters_checked(admin_page, "ac")
    items(admin_page).select_option(index=0)
    expect_letters_checked(admin_page, "b")
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PAIRS") == ["b", "a,c"]


def test_a_multiple_select_adds_and_loads_every_chosen_value(admin_page, settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"letters": {**LETTER_LIST, "form": "tests.custom_types.LettersSelectField"}}}
    open_config(admin_page, "PAIRS", "list:letters", ["b"])
    picker = admin_page.locator("select[name=value__item]")
    picker.select_option(["a", "c"])
    button(admin_page, "Add").click()
    expect(options(admin_page)).to_have_text(["b", "a,c"])
    expect(picker).to_have_values([])
    items(admin_page).select_option(index=1)
    expect(picker).to_have_values(["a", "c"])
    items(admin_page).select_option(index=0)
    expect(picker).to_have_values(["b"])
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert stored("PAIRS") == ["b", "a,c"]


def wait_until_held(page, held):
    # Bounded: the request reaches the route within five seconds, or the test fails.
    for _ in range(250):
        if held:
            break
        page.wait_for_timeout(20)
    assert held, "the request never reached the check URL"


def test_typing_while_an_add_is_pending_is_kept(admin_page):
    held = []
    admin_page.goto(ADD.format("list:str"))
    admin_page.route("**/list-item/**", lambda route: held.append(route))
    item_input(admin_page).fill("first")
    button(admin_page, "Add").click()
    expect(button(admin_page, "Add")).to_be_disabled()
    item_input(admin_page).fill("second")
    wait_until_held(admin_page, held)
    held[0].continue_()
    expect(options(admin_page)).to_have_text(["first"])
    expect(item_input(admin_page)).to_have_value("second")
    # Still an item typed but not added.
    save(admin_page)
    expect(message(admin_page)).to_have_text("You have an unsaved change to an item: click Update or Clear.")


def test_the_arrow_keys_move_through_the_list(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["1", "2", "3", "4"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("1")
    items(admin_page).focus()
    for _ in range(3):
        admin_page.keyboard.press("ArrowDown")
    expect(items(admin_page)).to_have_js_property("selectedIndex", 3)
    expect(item_input(admin_page)).to_have_value("4")
    expect(items(admin_page)).to_be_focused()
    expect(button(admin_page, "Remove")).to_be_enabled()


def test_down_pressed_from_the_keyboard_keeps_its_focus(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["1", "2", "3", "4"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("1")
    button(admin_page, "Down").focus()
    admin_page.keyboard.press("Enter")
    admin_page.keyboard.press("Space")
    expect(options(admin_page)).to_have_text(["2", "3", "1", "4"])
    expect(button(admin_page, "Down")).to_be_focused()


def test_add_pressed_from_the_keyboard_keeps_its_focus(admin_page):
    # Add is disabled while the server checks the item, which drops focus; it gets it back with the answer.
    admin_page.goto(ADD.format("list:int"))
    item_input(admin_page).fill("7")
    button(admin_page, "Add").focus()
    admin_page.keyboard.press("Enter")
    expect(options(admin_page)).to_have_text(["7"])
    expect(button(admin_page, "Add")).to_be_focused()
    item_input(admin_page).fill("8")
    button(admin_page, "Add").focus()
    admin_page.keyboard.press("Space")
    expect(options(admin_page)).to_have_text(["7", "8"])
    expect(button(admin_page, "Add")).to_be_focused()


# Hold each request to the check URL until the test releases it, counting those sent on the page, so the test can wait
# for them with expect.
HOLD_CHECKS = """() => {
    const send = window.fetch;
    const held = [];
    let sent = 0;
    window.fetch = (...args) =>
        new Promise((resolve, reject) => {
            held.push(() => send(...args).then(resolve, reject));
            document.body.dataset.sent = String(++sent);
        });
    window.releaseCheck = () => held.shift()();
}"""


def test_only_the_last_item_chosen_while_one_loads_is_loaded(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["1", "2", "3", "4"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("1")
    admin_page.evaluate(HOLD_CHECKS)
    body = admin_page.locator("body")
    items(admin_page).focus()
    for _ in range(3):
        admin_page.keyboard.press("ArrowDown")
    # One load, for item 2; the later choices wait for its answer, and the list shows the last one.
    expect(body).to_have_attribute("data-sent", "1")
    expect(items(admin_page)).to_have_js_property("selectedIndex", 3)
    expect(items(admin_page)).to_be_enabled()
    admin_page.evaluate("() => window.releaseCheck()")
    # Item 2's answer is out of date, so it isn't applied; item 4 loads instead.
    expect(body).to_have_attribute("data-sent", "2")
    expect(item_input(admin_page)).to_have_value("1")
    expect(items(admin_page)).to_have_js_property("selectedIndex", 3)
    admin_page.evaluate("() => window.releaseCheck()")
    expect(item_input(admin_page)).to_have_value("4")
    expect(button(admin_page, "Update")).to_be_enabled()
    expect(items(admin_page)).to_be_focused()


def test_typing_while_an_update_is_pending_is_an_unfinished_change(admin_page):
    held = []
    open_config(admin_page, "NAMES", "list:str", ["a", "b"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("a")
    admin_page.route("**/list-item/**", lambda route: held.append(route))
    item_input(admin_page).fill("first")
    button(admin_page, "Update").click()
    expect(button(admin_page, "Update")).to_be_disabled()
    item_input(admin_page).fill("second")
    wait_until_held(admin_page, held)
    held[0].continue_()
    expect(options(admin_page)).to_have_text(["first", "b"])
    expect(item_input(admin_page)).to_have_value("second")
    save(admin_page)
    expect(message(admin_page)).to_have_text("You have an unsaved change to an item: click Update or Clear.")
    assert stored("NAMES") == ["a", "b"]


def test_a_refused_item_keeps_its_error_over_an_item_chosen_meanwhile(admin_page):
    open_config(admin_page, "NAMES", "set:str", ["a", "b", "c"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("a")
    admin_page.evaluate(HOLD_CHECKS)
    item_input(admin_page).fill("b")
    button(admin_page, "Update").click()
    expect(admin_page.locator("body")).to_have_attribute("data-sent", "1")
    items(admin_page).select_option(index=2)
    admin_page.evaluate("() => window.releaseCheck()")
    expect(message(admin_page)).to_have_text("That's already in the set.")
    expect(items(admin_page)).to_have_js_property("selectedIndex", 0)
    expect(item_input(admin_page)).to_have_value("b")
    expect(admin_page.locator("body")).to_have_attribute("data-sent", "1")


def test_remove_pressed_from_the_keyboard_leaves_the_focus_on_the_list(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["1", "2", "3"])
    items(admin_page).select_option(index=0)
    expect(item_input(admin_page)).to_have_value("1")
    button(admin_page, "Remove").focus()
    admin_page.keyboard.press("Enter")
    expect(options(admin_page)).to_have_text(["2", "3"])
    expect(items(admin_page)).to_be_focused()


def test_down_onto_the_end_leaves_the_focus_on_the_list(admin_page):
    open_config(admin_page, "PORTS", "list:int", ["1", "2", "3"])
    items(admin_page).select_option(index=1)
    expect(item_input(admin_page)).to_have_value("2")
    button(admin_page, "Down").focus()
    admin_page.keyboard.press("Enter")
    expect(options(admin_page)).to_have_text(["1", "3", "2"])
    expect(button(admin_page, "Down")).to_be_disabled()
    expect(items(admin_page)).to_be_focused()
