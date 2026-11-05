"""Config overrides for the current context.

The test helpers set these and ``get``/``get_or_create`` read them first. They live in a ``ContextVar``, so each
thread and asyncio task sees its own, and ``sync_to_async`` carries them into the async API.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from types import MappingProxyType
from typing import Any

_EMPTY: Mapping[str, Any] = MappingProxyType({})
_current: ContextVar[Mapping[str, Any] | None] = ContextVar("dynamic_configs_overrides", default=None)


def current() -> Mapping[str, Any]:
    """Return the overrides active in this context (empty when there are none)."""
    return _current.get() or _EMPTY


def lookup(name: str) -> tuple[bool, Any]:
    """Return ``(True, value)`` if ``name`` is overridden here, otherwise ``(False, None)``."""
    values = current()
    # Overrides are keyed by keyword names, so only a string can be one; checking first also keeps an unhashable name
    # (a list, say) from raising here, before the caller's own name check.
    if isinstance(name, str) and name in values:
        return True, values[name]
    return False, None


def push(values: Mapping[str, Any]) -> Token[Mapping[str, Any] | None]:
    """Layer ``values`` over the active overrides; return the token that ``pop`` needs to undo it."""
    return _current.set(MappingProxyType({**current(), **values}))


def pop(token: Token[Mapping[str, Any] | None]) -> None:
    """Undo the ``push`` that returned ``token``."""
    _current.reset(token)


def replace(values: Mapping[str, Any]) -> None:
    """Make ``values`` the active overrides (used where push/pop can't pair up, such as pytest fixtures)."""
    _current.set(MappingProxyType(dict(values)))
