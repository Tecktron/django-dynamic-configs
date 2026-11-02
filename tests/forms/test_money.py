from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dynamic_configs.forms.money import MoneyCurrencyField, MoneyCurrencyWidget, MoneyField
from dynamic_configs.types.money import Money


def test_the_amount_field_allows_at_most_two_places():
    assert MoneyField().clean("9.9") == Decimal("9.9")
    for text in ("9.990", "9.999"):
        with pytest.raises(ValidationError):
            MoneyField().clean(text)


def test_the_currency_field_combines_amount_and_currency():
    assert MoneyCurrencyField().clean(["9.99", "cad"]) == Money(Decimal("9.99"), "CAD")


def test_an_empty_optional_currency_field_is_none():
    assert MoneyCurrencyField(required=False).clean(["", ""]) is None


@pytest.mark.parametrize(
    ("data", "message"),
    [(["9.99", ""], "both"), (["", "CAD"], "both"), (["9.99", "CADX"], "at most 3"), (["9.99", "C1D"], "3-letter")],
)
def test_the_currency_field_reports_bad_input(data, message):
    with pytest.raises(ValidationError, match=message):
        MoneyCurrencyField(required=False).clean(data)


def test_the_widget_splits_money_into_its_parts():
    widget = MoneyCurrencyWidget()
    assert widget.decompress(Money(Decimal("9.99"), "CAD")) == [Decimal("9.99"), "CAD"]
    assert widget.decompress(None) == [None, None]
