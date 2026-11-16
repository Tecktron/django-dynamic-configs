import decimal
from decimal import Decimal

import pytest
from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.forms.fields import formfield_for
from dynamic_configs.forms.money import MoneyCurrencyField, MoneyCurrencyWidget, MoneyField
from dynamic_configs.types.money import Money, MoneySerializer
from dynamic_configs.types.registry import load_custom_type


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


def test_the_amount_field_with_rounding_takes_more_places_and_keeps_its_step():
    field = MoneyField(rounding=decimal.ROUND_HALF_UP)
    assert field.clean("9.946") == Decimal("9.946")
    assert field.widget.attrs["step"] == "0.01"
    assert MoneyField().widget.attrs["step"] == "0.01"


def test_the_amount_field_without_rounding_refuses_three_places():
    with pytest.raises(ValidationError):
        MoneyField(rounding=None).clean("9.946")


def test_the_currency_field_with_rounding_rounds_the_amount():
    field = MoneyCurrencyField(rounding=decimal.ROUND_HALF_UP)
    assert field.clean(["9.946", "cad"]) == Money(Decimal("9.95"), "CAD")


def test_the_currency_field_without_rounding_refuses_three_places():
    with pytest.raises(ValidationError):
        MoneyCurrencyField().clean(["9.946", "cad"])


@pytest.mark.parametrize(
    ("key", "serializer", "form"),
    [
        ("money", "MoneySerializer", "MoneyField"),
        ("money_currency", "MoneyCurrencySerializer", "MoneyCurrencyField"),
    ],
)
def test_formfield_for_gives_the_field_the_serializers_rounding(key, serializer, form):
    entry = {
        "type": "decimal.Decimal" if key == "money" else "dynamic_configs.types.money.Money",
        "serializer": f"dynamic_configs.types.money.{serializer}",
        "form": f"dynamic_configs.forms.money.{form}",
    }
    plain = formfield_for(load_custom_type(key, entry))
    rounding = formfield_for(load_custom_type(key, {**entry, "options": {"rounding": "ROUND_HALF_UP"}}))
    amount = ["9.946", "CAD"] if key == "money_currency" else "9.946"
    with pytest.raises(ValidationError):
        plain.clean(amount)
    assert rounding.clean(amount) is not None


def test_another_form_gets_no_rounding_keyword_and_keeps_its_own_validation():
    entry = {
        "type": "decimal.Decimal",
        "serializer": "dynamic_configs.types.money.MoneySerializer",
        "form": "django.forms.DecimalField",
        "options": {"rounding": "ROUND_UP"},
    }
    field = formfield_for(load_custom_type("money", entry), decimal_places=2)
    with pytest.raises(ValidationError):
        field.clean("9.946")


class ProjectMoneyField(MoneyField):
    """A project's own subclass."""


def test_a_subclass_of_the_money_field_gets_the_rounding():
    entry = {
        "type": "decimal.Decimal",
        "serializer": "dynamic_configs.types.money.MoneySerializer",
        "form": "tests.forms.test_money.ProjectMoneyField",
        "options": {"rounding": "ROUND_HALF_UP"},
    }
    field = formfield_for(load_custom_type("money", entry))
    assert isinstance(field, ProjectMoneyField)
    assert field.clean("9.946") == Decimal("9.946")
    assert MoneySerializer(rounding="ROUND_HALF_UP").serialize(field.clean("9.946")) == "9.95"


@pytest.mark.parametrize("rounding", [None, decimal.ROUND_HALF_UP])
def test_the_currency_fields_amount_is_the_money_fields_number_input(rounding):
    amount = MoneyCurrencyField(rounding=rounding).widget.widgets[0]
    assert type(amount) is forms.NumberInput
    assert amount.attrs["step"] == "0.01"
