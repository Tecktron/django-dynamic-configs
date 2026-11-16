import decimal
from decimal import Decimal

import pytest
from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.forms.fields import formfield_for
from dynamic_configs.forms.money import MoneyCurrencyField, MoneyCurrencyWidget, MoneyField
from dynamic_configs.types import iso4217
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


def render_currency(**kwargs):
    attrs = kwargs.pop("attrs", {"id": "id_value"})
    return MoneyCurrencyField(**kwargs).widget.render("value", None, attrs)


def test_the_currency_input_points_at_a_datalist_of_suggestions_inside_the_span():
    html = render_currency()
    assert 'list="id_value_1_currencies"' in html
    assert '<datalist id="id_value_1_currencies">' in html
    assert '<option value="CAD">Canadian Dollar</option>' in html
    assert html.count("<option") == len(iso4217.CURRENCIES)
    assert html.startswith("<span>")
    assert html.endswith("</datalist></span>")
    # Only the currency input points at it.
    [amount, currency] = html.split("<input")[1:]
    assert "list=" not in amount
    assert 'name="value_1"' in currency
    assert 'list="id_value_1_currencies"' in currency


def test_the_datalists_id_comes_from_the_name_without_an_id():
    html = render_currency(attrs={})
    assert 'list="value_1_currencies"' in html
    assert '<datalist id="value_1_currencies">' in html


def test_a_widget_with_no_currencies_has_no_datalist():
    html = render_currency(currencies={})
    assert "list=" not in html
    assert "<datalist" not in html


def test_a_label_is_escaped_and_an_empty_one_leaves_the_option_empty():
    html = render_currency(currencies={"ABC": "<b>x</b>", "DEF": ""})
    assert '<option value="ABC">&lt;b&gt;x&lt;/b&gt;</option>' in html
    assert "<b>" not in html
    assert '<option value="DEF"></option>' in html


def test_the_widget_takes_its_own_currencies():
    widget = MoneyCurrencyWidget(currencies={"CAD": "Loonie"})
    assert '<option value="CAD">Loonie</option>' in widget.render("value", None, {"id": "id_value"})
    assert "<datalist" in MoneyCurrencyWidget().render("value", None)


def test_suggestions_do_not_restrict_the_currency_field():
    assert MoneyCurrencyField(currencies={}).clean(["9.99", "xyz"]) == Money(Decimal("9.99"), "XYZ")
    assert MoneyCurrencyField(currencies={"CAD": "Loonie"}).clean(["9.99", "xyz"]) == Money(Decimal("9.99"), "XYZ")


def test_the_item_editors_widgets_get_context_names_each_datalist_after_its_input():
    widget = MoneyCurrencyField().widget
    context = widget.get_context("value__item", None, {"id": "id_value__item"})
    assert context["widget"]["subwidgets"][1]["attrs"]["list"] == "id_value__item_1_currencies"
    assert "list" not in context["widget"]["subwidgets"][0]["attrs"]


class ProjectCurrencyField(MoneyCurrencyField):
    """A project's own subclass."""


@pytest.mark.parametrize("form", ["MoneyCurrencyField", "ProjectCurrencyField"])
def test_formfield_for_gives_the_currency_field_the_serializers_currencies(form):
    entry = {
        "type": "dynamic_configs.types.money.Money",
        "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
        "form": f"tests.forms.test_money.{form}"
        if form.startswith("Project")
        else f"dynamic_configs.forms.money.{form}",
    }
    narrowed = formfield_for(load_custom_type("money_currency", {**entry, "options": {"currencies": ["CAD"]}}))
    assert narrowed.currencies == {"CAD": "Canadian Dollar"}
    empty = formfield_for(load_custom_type("money_currency", {**entry, "options": {"currencies": []}}))
    assert empty.currencies == {}
    assert formfield_for(load_custom_type("money_currency", entry)).currencies == iso4217.CURRENCIES


def test_formfield_for_gives_no_currencies_to_the_money_field_or_another_form():
    money = {
        "type": "decimal.Decimal",
        "serializer": "dynamic_configs.types.money.MoneySerializer",
        "form": "dynamic_configs.forms.money.MoneyField",
    }
    assert not hasattr(formfield_for(load_custom_type("money", money)), "currencies")
    other = {
        "type": "dynamic_configs.types.money.Money",
        "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
        "form": "django.forms.CharField",
        "options": {"currencies": ["CAD"]},
    }
    assert isinstance(formfield_for(load_custom_type("money_currency", other)), forms.CharField)


def test_formfield_for_a_serializer_without_currencies_leaves_the_fields_default():
    config_type = load_custom_type(
        "money_currency",
        {
            "type": "dynamic_configs.types.money.Money",
            "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
            "form": "dynamic_configs.forms.money.MoneyCurrencyField",
        },
    )
    del config_type.serializer.currencies
    assert formfield_for(config_type).currencies == iso4217.CURRENCIES


class BoxedCurrencyWidget(MoneyCurrencyWidget):
    """A project's own widget built on the money one."""


class BoxedWidgetField(MoneyCurrencyField):
    widget = BoxedCurrencyWidget


class UnrelatedWidgetField(MoneyCurrencyField):
    widget = forms.TextInput


def test_a_subclass_widget_built_on_the_money_widget_gets_the_number_amount_and_the_datalist():
    widget = BoxedWidgetField(currencies={"CAD": "Loonie"}).widget
    assert type(widget) is BoxedCurrencyWidget
    assert widget.widgets[0].input_type == "number"
    assert '<option value="CAD">Loonie</option>' in widget.render("value", None, {"id": "id_value"})


def test_a_subclass_widget_that_is_not_the_money_widget_is_left_to_django():
    assert type(UnrelatedWidgetField().widget) is forms.TextInput


def test_an_explicit_widget_wins_over_the_classs():
    assert type(BoxedWidgetField(widget=forms.HiddenInput).widget) is forms.HiddenInput
    assert type(MoneyCurrencyField(widget=forms.HiddenInput).widget) is forms.HiddenInput


class InstanceWidgetField(MoneyCurrencyField):
    widget = MoneyCurrencyWidget(currencies={"CAD": "Loonie"})


class InstanceTextInputField(MoneyCurrencyField):
    widget = forms.TextInput()


def test_a_subclass_widget_instance_is_kept_as_the_project_made_it():
    html = InstanceWidgetField().widget.render("value", None, {"id": "id_value"})
    assert '<option value="CAD">Loonie</option>' in html
    assert 'value="USD"' not in html


def test_a_subclass_text_input_instance_is_copied_not_shared():
    widget = InstanceTextInputField().widget
    assert type(widget) is forms.TextInput
    assert widget is not InstanceTextInputField.widget
