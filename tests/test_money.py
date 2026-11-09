from decimal import Decimal

import pytest

import dynamic_configs
from dynamic_configs.exceptions import ConfigValueError
from dynamic_configs.models import Config
from dynamic_configs.types.money import Money

pytestmark = pytest.mark.django_db

MONEY_TYPES = {
    "money": {
        "type": "decimal.Decimal",
        "serializer": "dynamic_configs.types.money.MoneySerializer",
        "form": "dynamic_configs.forms.money.MoneyField",
        "label": "Money",
        "help_text": "An amount with at most 2 decimal places, e.g. 9.99",
    },
    "money_currency": {
        "type": "dynamic_configs.types.money.Money",
        "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
        "form": "dynamic_configs.forms.money.MoneyCurrencyField",
        "label": "Money with currency",
        "help_text": "An amount with at most 2 decimal places, and a 3-letter currency code",
        "raw_help_text": "An amount with at most 2 decimal places and a 3-letter currency code, e.g. 9.99 CAD",
    },
}


@pytest.fixture(autouse=True)
def _money_types(settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": MONEY_TYPES}


def test_money_amounts_round_trip_through_the_api():
    assert dynamic_configs.get_or_create("PRICE", "money", Decimal("9.9")) == (Decimal("9.90"), True)
    assert Config.objects.get(name="PRICE").value == "9.90"
    assert dynamic_configs.get_or_create("FEE", "money", 5) == (Decimal("5.00"), True)


def test_money_rejects_extra_places_from_code():
    with pytest.raises(ConfigValueError, match="at most 2"):
        dynamic_configs.get_or_create("RATE", "money", Decimal("9.999"))


def test_money_with_currency_and_its_set_variant():
    price = Money(Decimal("9.99"), "CAD")
    assert dynamic_configs.get_or_create("PRICE", "money_currency", price) == (price, True)
    prices = [Money(Decimal("1"), "USD"), Money(Decimal("2"), "EUR")]
    value, _ = dynamic_configs.get_or_create("PRICES", "set:money_currency", prices)
    assert value == frozenset(prices)
    assert Config.objects.get(name="PRICES").value == '["1.00 USD", "2.00 EUR"]'


def test_a_list_of_money_with_currency_has_help_for_its_boxes_and_for_typing(admin_client):
    content = admin_client.get("/admin/dynamic_configs/config/add/?type=list:money_currency").content.decode()
    # The item editor is an amount box and a currency box; raw mode types both on one line.
    assert '<p class="help">An amount with at most 2 decimal places, and a 3-letter currency code</p>' in content
    assert (
        '<p class="help">One item per line. Each item: An amount with at most 2 decimal places and a 3-letter '
        "currency code, e.g. 9.99 CAD</p>"
    ) in content


def test_money_in_the_admin(admin_client):
    url = "/admin/dynamic_configs/config/"
    response = admin_client.post(
        f"{url}add/?type=money_currency",
        {"name": "PRICE", "value_0": "9.99", "value_1": "cad", "description": "", "_save": "Save"},
    )
    assert response.status_code == 302
    assert Config.objects.get(name="PRICE").value == "9.99 CAD"
    content = admin_client.get(f"{url}PRICE/change/").content.decode()
    assert 'name="value_0" value="9.99"' in content
    assert 'name="value_1" value="CAD"' in content
    response = admin_client.post(
        f"{url}PRICE/change/", {"value_0": "12.5", "value_1": "usd", "description": "", "_save": "Save"}
    )
    assert response.status_code == 302
    assert Config.objects.get(name="PRICE").value == "12.50 USD"


def test_a_set_of_money_rejects_the_same_amount_twice_in_the_admin(admin_client):
    response = admin_client.post(
        "/admin/dynamic_configs/config/add/?type=set:money_currency",
        {
            "name": "PRICES",
            "value": "9.99 CAD\n9.99 cad",
            "description": "",
            "_save": "Save",
        },
    )
    assert response.status_code == 200
    assert "Lines 1 and 2 are the same." in response.content.decode()
