"""Money and decimal inputs (admin.js): the arrows step from multiples of the step, in a real browser."""

from playwright.sync_api import expect

from dynamic_configs.models import Config

MONEY = {
    "money": {
        "type": "decimal.Decimal",
        "serializer": "dynamic_configs.types.money.MoneySerializer",
        "form": "dynamic_configs.forms.money.MoneyField",
        "label": "Money",
    },
}


def value_input(page):
    return page.locator("input[name=value]")


def save(page):
    page.get_by_role("button", name="Save", exact=True).click()


def open_price(page):
    Config.objects.create(name="PRICE", type="money", value="1.00")
    page.goto("/admin/dynamic_configs/config/PRICE/change/")


def test_money_arrows_step_from_whole_cents_after_a_refused_value(admin_page, settings):
    # The browser counted steps from the value the page was served with: up from a refused 1.234 went to 1.244.
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY}
    open_price(admin_page)
    value_input(admin_page).fill("1.234")
    save(admin_page)
    expect(admin_page.locator(".errorlist")).to_contain_text("no more than 2 decimal places")
    expect(value_input(admin_page)).to_have_value("1.234")
    value_input(admin_page).press("ArrowUp")
    expect(value_input(admin_page)).to_have_value("1.24")


def test_money_with_rounding_saves_more_places_as_typed(admin_page, settings):
    # Its input keeps step 0.01, but the script doesn't trim money: the server rounds it.
    settings.DYNAMIC_CONFIGS = {"TYPES": {"money": {**MONEY["money"], "options": {"rounding": "ROUND_HALF_UP"}}}}
    open_price(admin_page)
    value_input(admin_page).fill("9.946")
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert Config.objects.get(name="PRICE").value == "9.95"
