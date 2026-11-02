"""The form field for JSON settings."""

from __future__ import annotations

import json
from typing import Any

from django import forms

from dynamic_configs.forms.fields import SerializerField
from dynamic_configs.types.serializers import JSONSerializer


class JSONTextField(SerializerField):
    """A textarea for a JSON object or array, shown pretty-printed and validated on the server."""

    widget = forms.Textarea

    def __init__(self, **kwargs: Any) -> None:
        """Read the value with the JSON serializer."""
        super().__init__(JSONSerializer(), **kwargs)

    def prepare_value(self, value: Any) -> Any:
        """Show an object or array indented, for reading; leave text (re-displayed input) as it is."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, ensure_ascii=False)
        return super().prepare_value(value)
