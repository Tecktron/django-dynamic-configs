"""Typed runtime settings for Django that admins can add and edit, read through a small cached API.

The API is loaded on first use (a module ``__getattr__``), because this module is imported while Django is still
loading ``INSTALLED_APPS``, before models can be imported.
"""

import importlib
from importlib import metadata
from typing import Any

__version__ = metadata.version("django-dynamic-configs")

_LAZY = {
    "get": "dynamic_configs.api",
    "get_or_create": "dynamic_configs.api",
    "update": "dynamic_configs.api",
    "delete": "dynamic_configs.api",
    "ConfigError": "dynamic_configs.exceptions",
    "ConfigTypeError": "dynamic_configs.exceptions",
    "ConfigValueError": "dynamic_configs.exceptions",
    "ConfigDoesNotExist": "dynamic_configs.models",
}


def __getattr__(name: str) -> Any:
    """Return a public API name, importing the module that defines it on first use."""
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)
