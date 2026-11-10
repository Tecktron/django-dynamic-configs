"""Custom types used by the registry and system check tests."""

import re
from dataclasses import dataclass

from django import forms


@dataclass(frozen=True)
class Color:
    hex: str


class ColorSerializer:
    def serialize(self, value):
        return value.hex

    def deserialize(self, text):
        if not re.fullmatch(r"#[0-9a-f]{6}", text):
            raise ValueError("Enter a hex color such as #1a2b3c.")
        return Color(text)


class ColorField(forms.CharField):
    pass


class Unhashable:
    __hash__ = None


class UnhashableSerializer:
    def serialize(self, value):
        return "unhashable"

    def deserialize(self, text):
        return Unhashable()


class NeedsArgumentSerializer:
    def __init__(self, required):
        self.required = required


class NoMethodsSerializer:
    pass


def not_a_class():
    return None


class LeakySerializer:
    """Puts the text in its error message, as a custom serializer written for admin form errors might."""

    def serialize(self, value):
        return value

    def deserialize(self, text):
        raise ValueError(f"{text!r} isn't allowed")


class WrongTypeColorField(forms.CharField):
    """Returns a plain string where the Color type expects a Color, to test the admin's type check."""


class CodeEditorWidget(forms.Textarea):
    """Stands in for a third-party editor widget, which typically subclasses Textarea."""

    def __init__(self, attrs=None):
        super().__init__(attrs={"class": "code-editor", **(attrs or {})})


class CodeEditorColorField(forms.CharField):
    """A Color field edited in a code-editor widget, to test that the admin keeps a type's own widget."""

    widget = CodeEditorWidget


class UnstrippedColorField(forms.CharField):
    """A Color field that deliberately keeps the spaces typed in it, to test that STRIP_STRINGS leaves it alone."""

    def __init__(self, **kwargs):
        kwargs.setdefault("strip", False)
        super().__init__(**kwargs)


LETTERS = [("a", "A"), ("b", "B"), ("c", "C")]


class LetterField(forms.ChoiceField):
    """One letter chosen with radio buttons: an item editor whose inputs share a name."""

    widget = forms.RadioSelect

    def __init__(self, **kwargs):
        super().__init__(choices=LETTERS, **kwargs)


class LettersSerializer:
    """A list of letters, stored as comma-joined text."""

    def serialize(self, value):
        return ",".join(value)

    def deserialize(self, text):
        return text.split(",") if text else []


class LettersField(forms.MultipleChoiceField):
    """Several letters chosen with checkboxes: a multi-value item editor."""

    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        super().__init__(choices=LETTERS, **kwargs)


class LettersSelectField(LettersField):
    """Several letters chosen in a ``<select multiple>``."""

    widget = forms.SelectMultiple


def color_hex(color):
    """A sort key for Color, which defines no order."""
    return color.hex


def compare_colors(first, second):
    """A compare function for Color: negative, zero or positive."""
    return (first.hex > second.hex) - (first.hex < second.hex)


def failing_key(color):
    """A sort key that fails, as a project's buggy key might."""
    raise KeyError(color.hex)


NOT_CALLABLE = 5
