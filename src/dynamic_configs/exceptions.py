"""Exceptions raised by django-dynamic-configs.

``ConfigDoesNotExist`` lives in ``dynamic_configs.models`` because it subclasses the model's ``DoesNotExist``.
"""


class ConfigError(Exception):
    """Base class for this package's errors."""


class ConfigTypeError(ConfigError, TypeError):
    """A value has the wrong type for its config, a type key isn't registered, or a config exists with another type."""


class ConfigValueError(ConfigError, ValueError):
    """A name is invalid, a serializer rejects a value, or a stored value can't be read."""
