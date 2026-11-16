"""The currency suggestions of money with currency (a datalist), in a real browser."""

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
ADD = "/admin/dynamic_configs/config/add/?type={}"
# What each input's list holds in the browser: the number of suggestions, or null when the list doesn't resolve.
SUGGESTIONS = "element => element.list && element.list.options.length"


def use_types(settings, **options):
    settings.DYNAMIC_CONFIGS = {"TYPES": {"money_currency": {**MONEY_CURRENCY, "options": options}}}


def save(page):
    page.get_by_role("button", name="Save", exact=True).click()


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def test_the_currency_input_suggests_the_iso_list(admin_page, settings):
    use_types(settings)
    Config.objects.create(name="PRICE", type="money_currency", value="1.00 CAD")
    admin_page.goto(CHANGE.format("PRICE"))
    assert admin_page.locator("input[name=value_1]").evaluate(SUGGESTIONS) >= 100
    assert admin_page.locator("input[name=value_0]").evaluate(SUGGESTIONS) is None


def test_the_suggestions_are_the_option_the_project_gave(admin_page, settings):
    use_types(settings, currencies={"ABC": "<b>x</b>", "CAD": "Loonie"})
    Config.objects.create(name="PRICE", type="money_currency", value="1.00 CAD")
    admin_page.goto(CHANGE.format("PRICE"))
    assert admin_page.locator("input[name=value_1]").evaluate(SUGGESTIONS) == 2
    expect(admin_page.locator("datalist option")).to_have_count(2)
    # The label is text, not markup.
    assert admin_page.locator("datalist option").first.evaluate("el => el.textContent") == "ABC - <b>x</b>"
    assert admin_page.locator("datalist b").count() == 0


def test_no_currencies_means_no_datalist(admin_page, settings):
    use_types(settings, currencies=[])
    Config.objects.create(name="PRICE", type="money_currency", value="1.00 CAD")
    admin_page.goto(CHANGE.format("PRICE"))
    assert admin_page.locator("input[name=value_1]").get_attribute("list") is None
    expect(admin_page.locator("datalist")).to_have_count(0)


@pytest.mark.parametrize("currencies", [None, ["CAD"], []])
def test_a_typed_code_saves_whatever_is_suggested(admin_page, settings, currencies):
    use_types(settings, currencies=currencies)
    Config.objects.create(name="PRICE", type="money_currency", value="1.00 CAD")
    admin_page.goto(CHANGE.format("PRICE"))
    admin_page.locator("input[name=value_0]").fill("9.99")
    admin_page.locator("input[name=value_1]").fill("xyz")
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert Config.objects.get(name="PRICE").value == "9.99 XYZ"


def test_the_add_page_suggests_too(admin_page, settings):
    use_types(settings)
    admin_page.goto(ADD.format("money_currency"))
    assert admin_page.locator("input[name=value_1]").evaluate(SUGGESTIONS) >= 100
    admin_page.locator("input[name=name]").fill("PRICE")
    admin_page.locator("input[name=value_0]").fill("5")
    admin_page.locator("input[name=value_1]").fill("xyz")
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was added successfully")
    assert Config.objects.get(name="PRICE").value == "5.00 XYZ"


def test_a_list_of_money_has_a_datalist_per_input_with_unique_ids(admin_page, settings):
    use_types(settings)
    Config.objects.create(name="PRICES", type="list:money_currency", value=json.dumps(["1.00 CAD"]))
    admin_page.goto(CHANGE.format("PRICES"))
    # The item editor's currency input is named after the editor, not "value".
    assert admin_page.locator("input[name=value__item_1]").evaluate(SUGGESTIONS) >= 100
    ids = admin_page.locator("datalist").evaluate_all("lists => lists.map(list => list.id)")
    assert len(ids) == len(set(ids)) >= 1
    for currency in admin_page.locator("input[maxlength='3'][list]").all():
        assert currency.evaluate(SUGGESTIONS) >= 100


def test_an_item_with_a_typed_code_is_added_to_a_list(admin_page, settings):
    use_types(settings, currencies=["CAD"])
    Config.objects.create(name="PRICES", type="list:money_currency", value=json.dumps(["1.00 CAD"]))
    admin_page.goto(CHANGE.format("PRICES"))
    admin_page.locator("input[name=value__item_0]").fill("2.50")
    admin_page.locator("input[name=value__item_1]").fill("xyz")
    button(admin_page, "Add").click()
    save(admin_page)
    expect(admin_page.locator(".messagelist")).to_contain_text("was changed successfully")
    assert json.loads(Config.objects.get(name="PRICES").value) == ["1.00 CAD", "2.50 XYZ"]
