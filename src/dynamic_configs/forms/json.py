"""The form field for JSON settings."""

from __future__ import annotations

import json
from typing import Any

from django import forms

from dynamic_configs.forms.fields import SerializerField
from dynamic_configs.types.serializers import JSON_MAX_DEPTH, JSONSerializer


class JSONTextarea(forms.Textarea):
    """A textarea for JSON, marked for the admin's editor (``AdminJSONTextarea``), with spell-checking off.

    The editor reads the nesting limit (``JSON_MAX_DEPTH``) from ``data-dynamic-configs-json-max-depth``.
    """

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        """Add the marker and the nesting limit, and turn spell-checking off; ``attrs`` can override any of them."""
        super().__init__(
            {
                "data-dynamic-configs-json": True,
                "data-dynamic-configs-json-max-depth": JSON_MAX_DEPTH,
                "spellcheck": "false",
                **(attrs or {}),
            }
        )


class JSONTextField(SerializerField):
    """A textarea for a JSON object or array, shown pretty-printed and validated on the server."""

    widget = JSONTextarea

    def __init__(self, **kwargs: Any) -> None:
        """Read the value with the JSON serializer."""
        super().__init__(JSONSerializer(), **kwargs)

    def prepare_value(self, value: Any) -> Any:
        """Show an object or array indented, for reading; leave text (re-displayed input) as it is."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, ensure_ascii=False)
        return super().prepare_value(value)
