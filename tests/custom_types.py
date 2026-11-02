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
