"""Form fields for the money example types."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

from dynamic_configs.types import iso4217
from dynamic_configs.types.money import Money, check_amount


class MoneyField(forms.DecimalField):
    """An amount with at most 2 decimal places (Django counts the places as typed, so ``9.990`` is rejected).

    With ``rounding``, any number of places is accepted and the serializer rounds.
    """

    def __init__(self, rounding: str | None = None, **kwargs: Any) -> None:
        """Allow at most 2 decimal places, or any number when ``rounding`` is set.

        :param rounding: the type's rounding (``formfield_for`` passes it), or None
        """
        self.rounding = rounding
        if rounding is None:
            kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)
        if rounding is not None:
            # With no decimal_places Django's step is "any"; amounts are still entered in cents.
            self.widget.attrs["step"] = "0.01"


class MoneyCurrencyWidget(forms.MultiWidget):
    """An amount input and a 3-character currency input, side by side, with a datalist of suggested currencies.

    The suggestions are only suggestions: the currency input takes any 3 letters.
    """

    def __init__(
        self,
        attrs: dict[str, Any] | None = None,
        amount_widget: forms.Widget | None = None,
        currencies: Mapping[str, str] | None = None,
    ) -> None:
        """Create the amount and currency inputs.

        :param attrs: attributes for the widget as a whole
        :param amount_widget: the amount's input; ``MoneyField``'s own when None
        :param currencies: the codes to suggest, with their labels; the ISO 4217 list when None, none when empty
        """
        widgets = [
            MoneyField().widget if amount_widget is None else amount_widget,
            forms.TextInput(attrs={"size": 3, "maxlength": 3}),
        ]
        super().__init__(widgets, attrs)
        self.currencies = iso4217.CURRENCIES if currencies is None else currencies

    def datalist_id(self, name: str, attrs: dict[str, Any] | None) -> str:
        """Return the id of the datalist: the currency input's id (its name without one) and ``_currencies``."""
        widget_id = self.build_attrs(self.attrs, attrs).get("id")
        return f"{widget_id or name}_1_currencies"

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        """Point the currency input at its datalist, when there are currencies to suggest."""
        context = super().get_context(name, value, attrs)
        if self.currencies:
            context["widget"]["subwidgets"][1]["attrs"]["list"] = self.datalist_id(name, attrs)
        return context

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> SafeString:
        """Render both inputs and the datalist in one element, so the admin's flex layout keeps them side by side."""
        inputs = super().render(name, value, attrs, renderer)
        if not self.currencies:
            return format_html("<span>{}</span>", inputs)
        options = format_html_join("", '<option value="{}">{}</option>', self.currencies.items())
        return format_html(
            '<span>{}<datalist id="{}">{}</datalist></span>', inputs, self.datalist_id(name, attrs), options
        )

    def decompress(self, value: Any) -> list[Any]:
        """Split money into its amount and currency."""
        if isinstance(value, Money):
            return [value.amount, value.currency]
        return [None, None]


class MoneyCurrencyField(forms.MultiValueField):
    """An amount and a currency code, cleaned to ``Money`` (or None when both are empty)."""

    widget = MoneyCurrencyWidget

    def __init__(self, rounding: str | None = None, currencies: Mapping[str, str] | None = None, **kwargs: Any) -> None:
        """Combine ``MoneyField`` for the amount with a 3-character currency field.

        :param rounding: the type's rounding (``formfield_for`` passes it), or None
        :param currencies: the type's suggested currencies (``formfield_for`` passes them), or None for the ISO 4217
            list; suggestions only, any 3 letters are accepted
        """
        self.rounding = rounding
        self.currencies = iso4217.CURRENCIES if currencies is None else currencies
        amount = MoneyField(rounding=rounding)
        kwargs.setdefault("widget", MoneyCurrencyWidget(amount_widget=amount.widget, currencies=self.currencies))
        super().__init__((amount, forms.CharField(min_length=3, max_length=3)), **kwargs)

    def compress(self, data_list: list[Any]) -> Money | None:
        """Return ``Money`` from the cleaned amount and currency."""
        if not data_list or all(part in self.empty_values for part in data_list):
            return None
        amount, currency = data_list
        if amount in self.empty_values or currency in self.empty_values:
            raise ValidationError("Enter both an amount and a currency code.")
        try:
            return Money(check_amount(amount, self.rounding), currency.upper())
        except ValueError as error:
            raise ValidationError(str(error)) from error
