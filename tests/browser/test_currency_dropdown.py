"""The admin's currency dropdown (suggestions.js), in a real browser."""

import json

import pytest
from playwright.sync_api import expect

from dynamic_configs.models import Config

MONEY_CURRENCY = {
    "type": "dynamic_configs.types.money.Money",
    "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
    "form": "dynamic_configs.forms.money.MoneyCurrencyField",
    "label": "Money with currency",
}
CHANGE = "/admin/dynamic_configs/config/{}/change/"
DROPDOWN = ".dynamic-configs-suggestions"
# Whether the centre of the third option inside the dropdown's visible box is that option, not something over it.
THIRD_OPTION_ON_TOP = """list => {
    const box = list.getBoundingClientRect();
    const visible = [...list.querySelectorAll("[role=option]")].filter((option) => {
        const rect = option.getBoundingClientRect();
        return rect.top >= box.top && rect.bottom <= box.bottom;
    });
    const rect = visible[2].getBoundingClientRect();
    return document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2) === visible[2];
}"""
# Wait for the frame after a scroll, whose scroll events come before its animation frame callbacks.
NEXT_FRAME = "() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"


def use_types(settings, **options):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"money_currency": {**MONEY_CURRENCY, "options": options}}}


def save(page):
    page.get_by_role("button", name="Save", exact=True).click()


def open_price(page, settings, **options):
    """Open the change page of a ``PRICE`` of ``1.00 CAD``; return its currency input and the dropdown."""
    use_types(settings, **options)
    Config.objects.create(name="PRICE", type="money_currency", value="1.00 CAD")
    page.goto(CHANGE.format("PRICE"))
    return page.locator("input[name=value_1]"), page.locator(DROPDOWN)


def open_prices(page, settings):
    """Open a list of money with currency, with the item editor's amount filled in; return its currency input."""
    use_types(settings, currencies=["CAD", "USD"])
    Config.objects.create(name="PRICES", type="list:money_currency", value=json.dumps(["1.00 CAD"]))
    page.goto(CHANGE.format("PRICES"))
    page.locator("input[name=value__item_0]").fill("2.50")
    return page.locator("input[name=value__item_1]")


def items(page):
    return page.get_by_role("listbox", name="Items").locator("option")


def type_and_highlight(currency, text):
    currency.fill("")
    currency.press_sequentially(text)
    currency.press("ArrowDown")


def test_one_click_opens_the_list_with_codes_and_names(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    currency.click()
    expect(dropdown).to_be_visible()
    suggested = admin_page.locator("#id_value_1_currencies option").count()
    expect(dropdown.locator("[role=option]")).to_have_count(suggested)
    expect(dropdown.get_by_text("USD - US Dollar", exact=True)).to_have_count(1)
    expect(currency).to_have_attribute("aria-expanded", "true")
    assert currency.get_attribute("list") is None


def test_the_current_code_is_highlighted(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    currency.click()
    highlighted = dropdown.locator("[aria-selected=true]")
    expect(highlighted).to_have_attribute("data-value", "CAD")
    expect(highlighted).to_be_in_viewport()


def test_typing_filters_codes_first(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    currency.fill("")
    currency.press_sequentially("ca")
    options = dropdown.locator("[role=option]")
    expect(options.first).to_have_attribute("data-value", "CAD")
    for code, text in options.evaluate_all("all => all.map(option => [option.dataset.value, option.textContent])"):
        assert code.startswith("CA") or "ca" in text.lower()
    currency.fill("")
    currency.press_sequentially("qqq")
    expect(dropdown).to_be_hidden()


def test_arrows_and_enter_pick_without_saving(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    type_and_highlight(currency, "us")
    currency.press("Enter")
    expect(currency).to_have_value("USD")
    expect(dropdown).to_be_hidden()
    expect(admin_page.locator(".messagelist")).to_have_count(0)
    assert Config.objects.get(name="PRICE").value == "1.00 CAD"


def test_enter_without_a_highlight_still_saves(admin_page, settings):
    currency, _ = open_price(admin_page, settings)
    currency.fill("xyz")
    currency.press("Enter")
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert Config.objects.get(name="PRICE").value == "1.00 XYZ"


def test_clicking_an_option_picks_it(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    currency.click()
    dropdown.locator("[data-value=EUR]").click()
    expect(currency).to_have_value("EUR")
    expect(dropdown).to_be_hidden()
    expect(currency).to_be_focused()


@pytest.mark.parametrize("leave", ["Escape", "Tab", "click away"])
def test_escape_tab_and_clicking_away_never_pick(admin_page, settings, leave):
    currency, dropdown = open_price(admin_page, settings)
    type_and_highlight(currency, "us")
    expect(dropdown.locator("[aria-selected=true]")).to_have_count(1)
    if leave == "click away":
        admin_page.locator("h1").click()
    else:
        currency.press(leave)
    expect(dropdown).to_be_hidden()
    expect(currency).to_have_value("us")


def test_the_list_is_not_clipped_and_sits_under_the_input(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    # Room to scroll the window, below the form.
    admin_page.evaluate("document.body.style.paddingBottom = '200vh'")
    currency.click()
    expect(dropdown).to_be_visible()

    def check():
        input_box, list_box = currency.bounding_box(), dropdown.bounding_box()
        assert abs(list_box["y"] - (input_box["y"] + input_box["height"])) <= 2
        assert abs(list_box["x"] - input_box["x"]) <= 2
        assert dropdown.evaluate(THIRD_OPTION_ON_TOP)

    check()
    admin_page.evaluate("window.scrollBy(0, 50)")
    admin_page.evaluate(NEXT_FRAME)
    assert admin_page.evaluate("window.scrollY") == 50
    check()


def test_a_label_is_text_not_markup(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings, currencies={"ABC": "<b>x</b>"})
    currency.click()
    expect(dropdown.locator("[role=option]")).to_have_text(["ABC - <b>x</b>"])
    expect(dropdown.locator("b")).to_have_count(0)


@pytest.mark.browser_context_args(color_scheme="dark")
def test_dark_mode_uses_the_admins_colours(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings)
    currency.click()
    expect(dropdown).to_be_visible()
    body = admin_page.evaluate(
        "[getComputedStyle(document.body).color, getComputedStyle(document.body).backgroundColor]"
    )
    assert dropdown.evaluate("list => [getComputedStyle(list).color, getComputedStyle(list).backgroundColor]") == body
    # The dark admin's text is light: this runs in the dark scheme.
    assert body[0] != "rgb(51, 51, 51)"


def test_the_item_editor_picks_and_adds(admin_page, settings):
    currency = open_prices(admin_page, settings)
    currency.click()
    admin_page.locator(DROPDOWN).locator("[data-value=USD]").click()
    expect(currency).to_have_value("USD")
    expect(admin_page.locator(DROPDOWN)).to_be_hidden()
    currency.press("Enter")
    expect(items(admin_page)).to_have_count(2)
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert json.loads(Config.objects.get(name="PRICES").value) == ["1.00 CAD", "2.50 USD"]


def test_enter_on_a_highlight_does_not_add_the_item(admin_page, settings):
    currency = open_prices(admin_page, settings)
    type_and_highlight(currency, "us")
    currency.press("Enter")
    expect(currency).to_have_value("USD")
    expect(items(admin_page)).to_have_count(1)


def test_no_suggestions_no_dropdown(admin_page, settings):
    currency, dropdown = open_price(admin_page, settings, currencies=[])
    currency.click()
    expect(dropdown).to_have_count(0)
    assert currency.get_attribute("role") is None
