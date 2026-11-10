"""Form fields for the money example types."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.types.money import Money


class MoneyField(forms.DecimalField):
    """An amount with at most 2 decimal places (Django counts the places as typed, so ``9.990`` is rejected)."""

    def __init__(self, **kwargs: Any) -> None:
        """Allow at most 2 decimal places."""
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)


class MoneyCurrencyWidget(forms.MultiWidget):
    """An amount input and a 3-character currency input, side by side (no JavaScript)."""

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Create the amount and currency inputs."""
        widgets = [
            forms.TextInput(attrs={"inputmode": "decimal", "size": 10}),
            forms.TextInput(attrs={"size": 3, "maxlength": 3}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value: Any) -> list[Any]:
        """Split money into its amount and currency."""
        if isinstance(value, Money):
            return [value.amount, value.currency]
        return [None, None]


class MoneyCurrencyField(forms.MultiValueField):
    """An amount and a currency code, cleaned to ``Money`` (or None when both are empty)."""

    widget = MoneyCurrencyWidget

    def __init__(self, **kwargs: Any) -> None:
        """Combine ``MoneyField`` for the amount with a 3-character currency field."""
        super().__init__((MoneyField(), forms.CharField(min_length=3, max_length=3)), **kwargs)

    def compress(self, data_list: list[Any]) -> Money | None:
        """Return ``Money`` from the cleaned amount and currency."""
        if not data_list or all(part in self.empty_values for part in data_list):
            return None
        amount, currency = data_list
        if amount in self.empty_values or currency in self.empty_values:
            raise ValidationError("Enter both an amount and a currency code.")
        try:
            return Money(amount, currency.upper())
        except ValueError as error:
            raise ValidationError(str(error)) from error
