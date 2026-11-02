"""A config type: its Python type, serializer and admin details, plus the type check."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from dynamic_configs.exceptions import ConfigTypeError, ConfigValueError

# bool is a subclass of int in Python, so True would otherwise pass as a number.
_NUMBER_TYPES = (int, float, Decimal)


class Serializer(Protocol):
    """Converts a value to the text stored in the database and back, raising ValueError when it isn't allowed."""

    def serialize(self, value: Any) -> str:
        """Return the text to store for ``value``."""

    def deserialize(self, text: str) -> Any:
        """Return the value stored as ``text``."""


@dataclass(frozen=True)
class ConfigType:
    """One registered type; ``key`` is what ``Config.type`` stores.

    List and set variants have ``container`` set to ``"list"`` or ``"set"`` and ``item_type`` set to the type of
    their items.
    """

    key: str
    label: str
    python_type: type | tuple[type, ...]
    serializer: Serializer
    help_text: str = ""
    listable: bool = True
    # A form field class, or a callable that returns a field (a functools.partial setting a widget, say).
    form_class: Callable[..., Any] | None = None
    item_type: ConfigType | None = None
    container: Literal["list", "set"] | None = None

    @property
    def hashable(self) -> bool:
        """Return whether values of this type can go in a set, so the type can have a set variant."""
        return isinstance(self.python_type, type) and self.python_type.__hash__ is not None

    def coerce(self, value: Any) -> Any:
        """Check ``value`` against this type and return it as code reading the config would get it.

        :param value: the value to check
        :returns: the value, with an ``int`` converted for ``float``/``Decimal`` types, a list for list types and a
            frozenset for set types
        :raises ConfigTypeError: the value, or an item, has the wrong type
        :raises ConfigValueError: a set type was given a list or tuple containing the same item twice
        """
        if self.container is None:
            return self._coerce_scalar(value)
        items = self._coerce_items(value)
        return items if self.container == "list" else frozenset(items)

    def to_text(self, value: Any) -> str:
        """Return the text to store for ``value``.

        :param value: the value to store
        :returns: the serialized text
        :raises ConfigTypeError: the value, or an item, has the wrong type
        :raises ConfigValueError: the serializer rejects the value, or a set type was given duplicates
        """
        # Containers are serialized from the ordered item list, so a set entered as a list keeps its order.
        checked = self._coerce_items(value) if self.container else self._coerce_scalar(value)
        try:
            return self.serializer.serialize(checked)
        except ValueError as error:
            raise ConfigValueError(str(error)) from error

    def from_text(self, text: str) -> Any:
        """Return the value stored as ``text``.

        :param text: stored text
        :returns: the value
        :raises ConfigValueError: the text can't be read as this type, or reading it failed in any other way
        """
        try:
            return self.serializer.deserialize(text)
        except ValueError as error:
            raise ConfigValueError(str(error)) from error
        except Exception as error:
            # Anything else (RecursionError on deeply nested JSON, a custom serializer's KeyError...) also means the
            # stored text is unreadable, so get() can still answer with its default. Only the class is named: the
            # exception's message may contain the stored value.
            raise ConfigValueError(f"Reading the stored text failed with {type(error).__name__}.") from error

    def _coerce_scalar(self, value: Any) -> Any:
        """Apply the type check to a single value."""
        expected = self.python_type
        if isinstance(value, bool) and expected in _NUMBER_TYPES:
            raise self._wrong_type(value)
        if expected is date and isinstance(value, datetime):
            raise self._wrong_type(value)
        if isinstance(value, int) and expected in (float, Decimal):
            return expected(value)
        if isinstance(value, expected):
            return value
        raise self._wrong_type(value)

    def _coerce_items(self, value: Any) -> list[Any]:
        """Check a list or set type's value and each of its items, returning the items in order."""
        if self.container == "list":
            allowed: tuple[type, ...] = (list, tuple)
            description = "a list or tuple"
        else:
            allowed = (list, tuple, set, frozenset)
            description = "a set, frozenset, list or tuple"
        if not isinstance(value, allowed):
            raise ConfigTypeError(f"Type {self.key!r} expects {description}, not {type(value).__name__}.")
        items = [self.item_type._coerce_scalar(item) for item in value]  # type: ignore[union-attr]
        if self.container == "set":
            seen: set[Any] = set()
            for position, item in enumerate(items, start=1):
                if item in seen:
                    raise ConfigValueError(f"Item {position} repeats an earlier item; a set can't contain duplicates.")
                seen.add(item)
        return items

    def _wrong_type(self, value: Any) -> ConfigTypeError:
        """Return the error for a value of the wrong type."""
        if isinstance(self.python_type, tuple):
            expected = " or ".join(cls.__name__ for cls in self.python_type)
        else:
            expected = self.python_type.__name__
        return ConfigTypeError(f"Type {self.key!r} expects {expected}, not {type(value).__name__}.")
