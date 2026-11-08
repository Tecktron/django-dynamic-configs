"""Form fields for lists and sets, and their widget.

A list arrives in one of two forms, and the widget's hidden mode input says which: the items' stored texts, from the
admin's list editor, read exactly so spaces, empty items and line breaks survive; or text with one item per line, from
the editor's raw mode, the admin without JavaScript, and the field anywhere else.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.safestring import SafeString

from dynamic_configs.exceptions import ConfigError, ConfigValueError
from dynamic_configs.types.base import ConfigType

# The widget's hidden inputs are named after the field with these suffixes: the items' stored texts as a JSON array,
# and which form the server reads ("list", or "raw" for the textarea).
ITEMS_SUFFIX = "__items"
MODE_SUFFIX = "__mode"
# The admin's item editor's inputs are named after the field with this suffix.
ITEM_SUFFIX = "__item"
LOCKED_NOTE = (
    "This list has an item with a line break, which one item per line can't show, so editing it needs JavaScript."
)
UNREADABLE = "The list couldn't be read. Reload the page and try again."


class StoredTexts(list):  # type: ignore[type-arg]
    """Items as their stored texts, as the list editor submits them, rather than values still to be serialized."""


class UnreadableItems(str):
    """List-mode data that isn't a JSON array of strings (a tampered or truncated request); cleaning it is an error."""

    __slots__ = ()


def has_line_break(text: str) -> bool:
    """Return whether ``text`` contains a line break, which one item per line can't show."""
    return "\n" in text or "\r" in text


def split_lines(text: str) -> list[str]:
    r"""Split ``text`` at its line breaks (``\r\n``, ``\r`` or ``\n``), as a textarea and the editor script do.

    Not ``str.splitlines``, which also splits at characters a textarea shows within a line (U+2028, say).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


class ListWidget(forms.Textarea):
    """A textarea of items, one per line, with hidden inputs holding the items' stored texts and the mode.

    The mode says raw (read the textarea) unless an item contains a line break: one item per line can't show it, so
    the textarea is read-only, the mode says list, and saving keeps the items exactly.
    """

    def format_value(self, value: Any) -> str | None:
        """Show stored texts one per line; leave text (input re-displayed after an error) as it is."""
        if isinstance(value, StoredTexts):
            return "\n".join(value)
        return super().format_value(value)

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> SafeString:
        """Render the textarea and its help, the hidden inputs, and a note when the list can't be edited as text."""
        texts = value if isinstance(value, StoredTexts) else None
        locked = texts is not None and any(has_line_break(text) for text in texts)
        if locked:
            attrs = {**(attrs or {}), "readonly": True}
        hidden = forms.HiddenInput()
        return format_html(
            '<div class="dynamic-configs-list-raw">{}<p class="help">One item per line.</p></div>{}{}{}',
            super().render(name, value, attrs, renderer),
            # null when the page shows text that isn't a list yet: the editor script then starts in raw mode.
            hidden.render(f"{name}{ITEMS_SUFFIX}", json.dumps(texts), renderer=renderer),
            hidden.render(f"{name}{MODE_SUFFIX}", "list" if locked else "raw", renderer=renderer),
            format_html('<p class="help dynamic-configs-list-locked">{}</p>', LOCKED_NOTE) if locked else "",
        )

    def value_from_datadict(self, data: Any, files: Any, name: str) -> Any:
        """Return the stored texts in list mode, otherwise the textarea's text."""
        if data.get(f"{name}{MODE_SUFFIX}") != "list":
            return super().value_from_datadict(data, files, name)
        try:
            texts = json.loads(data.get(f"{name}{ITEMS_SUFFIX}", ""))
        except (ValueError, RecursionError):
            # RecursionError: JSON nested too deeply, which Python's reader raises rather than a ValueError.
            return UnreadableItems()
        if not isinstance(texts, list) or not all(isinstance(text, str) for text in texts):
            return UnreadableItems()
        return StoredTexts(texts)


class LineListField(forms.CharField):
    """A list of strings; each line of raw text is stripped and blank lines are dropped.

    Validators (such as ``max_length``) run on each item, not on the list.
    """

    widget = ListWidget

    def __init__(self, **kwargs: Any) -> None:
        """Keep the text as typed; each line is prepared on its own (``line_text``)."""
        kwargs.setdefault("strip", False)
        super().__init__(**kwargs)

    def widget_attrs(self, widget: forms.Widget) -> dict[str, Any]:
        """Leave the length limits off the textarea: they apply to each item, which the browser can't check."""
        attrs = super().widget_attrs(widget)
        attrs.pop("maxlength", None)
        attrs.pop("minlength", None)
        return attrs

    def prepare_value(self, value: Any) -> Any:
        """Show a list as its items' stored texts; leave stored texts and text (re-displayed input) as they are."""
        if isinstance(value, (list, tuple)) and not isinstance(value, StoredTexts):
            return StoredTexts(self.item_to_text(item) for item in value)
        return value

    def item_to_text(self, item: Any) -> str:
        """Return the stored text of one item."""
        return str(item)

    def text_to_item(self, text: str, where: str) -> Any:
        """Return the item stored as ``text``; raise ValidationError starting with ``where`` ("Line 3") if invalid."""
        return text

    def line_text(self, line: str) -> str:
        """Return the item text on one line of raw text: stripped."""
        return line.strip()

    def numbered_items(self, value: Any) -> list[tuple[str, int, Any]]:
        """Return ``(noun, number, item)`` for each item, collecting every item's error.

        Stored texts are numbered as items ("Item 3"); raw text by line ("Line 3"), skipping blank lines.

        :raises ValidationError: the data can't be read, or items are invalid (one message each)
        """
        if isinstance(value, UnreadableItems):
            raise ValidationError(UNREADABLE)
        if isinstance(value, StoredTexts):
            numbered = [("Item", number, text) for number, text in enumerate(value, start=1)]
        else:
            text = super().to_python(value)
            numbered = [
                ("Line", number, self.line_text(line))
                for number, line in enumerate(split_lines(text), start=1)
                if line.strip()
            ]
        items: list[tuple[str, int, Any]] = []
        errors: list[str] = []
        for noun, number, item_text in numbered:
            try:
                items.append((noun, number, self.text_to_item(item_text, f"{noun} {number}")))
            except ValidationError as error:
                errors.extend(error.messages)
        if errors:
            raise ValidationError(errors)
        return items

    def to_python(self, value: Any) -> list[Any]:
        """Return the items, in order."""
        return [item for *_, item in self.numbered_items(value)]

    def run_validators(self, value: list[Any]) -> None:
        """Run the field's validators on each item."""
        for item in value:
            super().run_validators(item)


class TypedLineListField(LineListField):
    """A list of ``item_type`` values; with ``unique``, a set that rejects repeated items.

    ``item_field`` is the field for one item, as the admin's item editor shows it; the item helpers below are the list
    editor's checks, which the admin's check URL calls.
    """

    def __init__(self, item_type: ConfigType, *, unique: bool = False, **kwargs: Any) -> None:
        """Parse each item as ``item_type``; reject repeats when ``unique``."""
        # Imported here: dynamic_configs.forms.fields imports this module.
        from dynamic_configs.forms.fields import formfield_for

        self.item_type = item_type
        self.unique = unique
        self.item_field = formfield_for(item_type, item=True, required=False, label="Item")
        super().__init__(**kwargs)

    def item_to_text(self, item: Any) -> str:
        """Return the item as its type's stored text."""
        return self.item_type.serializer.serialize(item)

    def text_to_item(self, text: str, where: str) -> Any:
        """Parse one item's text as ``item_type``."""
        try:
            return self.item_type.from_text(text)
        except ConfigValueError as error:
            raise ValidationError(f"{where}: {error}") from error

    def line_text(self, line: str) -> str:
        """Strip a line of raw text as the item editor strips what's typed in it.

        A string follows ``STRIP_STRINGS``, multi-line text is kept, and other types are stripped: spaces around a
        number or a date are never part of it.
        """
        if isinstance(self.item_field, forms.CharField) and not self.item_field.strip:
            return line
        return line.strip()

    def to_python(self, value: Any) -> list[Any]:
        """Return the parsed items, in order; with ``unique``, reject items that repeat (compared after parsing)."""
        numbered = self.numbered_items(value)
        if self.unique:
            first_seen: dict[Any, int] = {}
            errors: list[str] = []
            for noun, number, item in numbered:
                if item in first_seen:
                    errors.append(f"{noun}s {first_seen[item]} and {number} are the same.")
                else:
                    first_seen[item] = number
            if errors:
                raise ValidationError(errors)
        return [item for *_, item in numbered]

    def item_text(
        self, data: Any, files: Any, name: str, *, others: Sequence[str] = (), position: int | None = None
    ) -> str:
        """Return the stored text of the item typed in the item editor, whose inputs are named after ``name``.

        :param others: the list's items as stored texts, for a set's repeat check
        :param position: the index of the item being updated, which isn't a repeat of itself
        :raises ValidationError: the item type's own error; "required" when the editor is empty and the type has no
            empty value; or a set's repeat
        """
        value = self.item_field.clean(self.item_field.widget.value_from_datadict(data, files, name))
        if value is None:
            raise ValidationError(self.item_field.error_messages["required"], code="required")
        try:
            text = self.item_type.to_text(value)
        except ConfigError as error:
            raise ValidationError(str(error)) from error
        if self.unique:
            item = self.item_type.from_text(text)
            if any(index != position and self._same(other, item) for index, other in enumerate(others)):
                raise ValidationError("That's already in the set.")
        return text

    def _same(self, text: str, item: Any) -> bool:
        """Return whether the stored ``text`` is ``item``; an unreadable item (a hand-edited row) is no one's repeat."""
        try:
            return self.item_type.from_text(text) == item
        except ConfigValueError:
            return False

    def editor_values(self, text: str, name: str) -> dict[str, Any]:
        """Return what each of the item editor's inputs (named after ``name``) shows for the item stored as ``text``.

        Each input's text, or for a checkbox whether it's checked. The page fills the inputs in, rather than replacing
        their HTML, so Django's widget scripts (the date picker, say) stay attached.

        :raises ValidationError: the stored text can't be read as the item type
        """
        try:
            value = self.item_type.from_text(text)
        except ConfigValueError as error:
            raise ValidationError(str(error)) from error
        widget = self.item_field.widget.get_context(name, self.item_field.prepare_value(value), {})["widget"]
        values: dict[str, Any] = {}
        for part in widget.get("subwidgets") or [widget]:
            if part.get("type") == "checkbox":
                values[part["name"]] = bool(part["attrs"].get("checked"))
            elif isinstance(part["value"], list):
                # A select: its one chosen value.
                values[part["name"]] = next(iter(part["value"]), "")
            else:
                values[part["name"]] = "" if part["value"] is None else str(part["value"])
        return values

    def sorted_texts(self, texts: Sequence[str], *, descending: bool) -> list[str]:
        """Return the stored ``texts`` in their values' order (see ``ConfigType.sort``).

        :raises ValidationError: an item can't be read, or the items can't be compared
        """
        values = [self.text_to_item(text, f"Item {number}") for number, text in enumerate(texts, start=1)]
        try:
            ordered = self.item_type.sort(values, descending=descending)
        except Exception as error:
            # Values that define no order raise TypeError; a project's key may raise anything. The list stays as is.
            raise ValidationError("These items can't be sorted.") from error
        return [self.item_type.to_text(value) for value in ordered]

    def texts_from_lines(self, lines: Sequence[str]) -> list[str]:
        """Return the stored texts of raw mode's ``lines``, checked as saving checks them.

        :raises ValidationError: one message per bad line ("Line 4: …"), and a set's repeats
        """
        return [self.item_type.to_text(item) for item in self.to_python("\n".join(lines))]
