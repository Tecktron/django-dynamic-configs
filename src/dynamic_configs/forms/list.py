"""Form fields for lists and sets entered one item per line."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from dynamic_configs.exceptions import ConfigValueError
from dynamic_configs.types.base import ConfigType


class LineListField(forms.CharField):
    """A list of strings edited in a textarea, one item per line.

    Each line is stripped and blank lines are dropped. Validators (such as ``max_length``) run on each item, not on
    the list.
    """

    widget = forms.Textarea

    def __init__(self, **kwargs: Any) -> None:
        """Keep the text as typed; each line is stripped on its own."""
        kwargs.setdefault("strip", False)
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        """Show a list as one item per line; leave text (re-displayed input) as it is."""
        if isinstance(value, (list, tuple)):
            return "\n".join(self.item_to_text(item) for item in value)
        return value

    def item_to_text(self, item: Any) -> str:
        """Return the text shown for one item."""
        return str(item)

    def parse_item(self, text: str, number: int) -> Any:
        """Return the item written on line ``number``; raise ValidationError naming the line if it's invalid."""
        return text

    def parse_lines(self, value: Any) -> list[tuple[int, Any]]:
        """Return ``(line number, item)`` for each non-blank line, collecting every line's error."""
        text = super().to_python(value)
        items: list[tuple[int, Any]] = []
        errors: list[str] = []
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append((number, self.parse_item(stripped, number)))
            except ValidationError as error:
                errors.extend(error.messages)
        if errors:
            raise ValidationError(errors)
        return items

    def to_python(self, value: Any) -> list[Any]:
        """Return the items, in order."""
        return [item for _, item in self.parse_lines(value)]

    def run_validators(self, value: list[Any]) -> None:
        """Run the field's validators on each item."""
        for item in value:
            super().run_validators(item)


class TypedLineListField(LineListField):
    """A list of ``item_type`` values, one per line; with ``unique``, a set that rejects repeated items."""

    def __init__(self, item_type: ConfigType, *, unique: bool = False, **kwargs: Any) -> None:
        """Parse each line as ``item_type``; reject repeats when ``unique``."""
        self.item_type = item_type
        self.unique = unique
        super().__init__(**kwargs)

    def item_to_text(self, item: Any) -> str:
        """Return the item as its type's stored text."""
        return self.item_type.serializer.serialize(item)

    def parse_item(self, text: str, number: int) -> Any:
        """Parse one line as ``item_type``."""
        try:
            return self.item_type.from_text(text)
        except ConfigValueError as error:
            raise ValidationError(f"Line {number}: {error}") from error

    def to_python(self, value: Any) -> list[Any]:
        """Return the parsed items, in order; with ``unique``, reject items that repeat (compared after parsing)."""
        lines = self.parse_lines(value)
        if self.unique:
            first_seen: dict[Any, int] = {}
            errors: list[str] = []
            for number, item in lines:
                if item in first_seen:
                    errors.append(f"Lines {first_seen[item]} and {number} are the same.")
                else:
                    first_seen[item] = number
            if errors:
                raise ValidationError(errors)
        return [item for _, item in lines]
