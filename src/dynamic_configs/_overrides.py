"""Config overrides for the current context.

The test helpers set these and ``get``/``get_or_create`` read them first. They live in a ``ContextVar``, so each
thread and asyncio task sees its own, and ``sync_to_async`` carries them into the async API.

They're kept as layers, the latest last, and the latest layer naming a config wins. ``push`` adds a layer that ``pop``
takes away again (a ``with`` block). ``pin`` adds one that outlasts the blocks open when it's added (the pytest
fixture's ``set()``, which lasts for the rest of the test).
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from types import MappingProxyType
from typing import Any, NamedTuple


class Layer(NamedTuple):
    """One set of overrides, and whether it outlasts the blocks open when it was added."""

    values: Mapping[str, Any]
    pinned: bool


_layers: ContextVar[tuple[Layer, ...]] = ContextVar("dynamic_configs_overrides", default=())


def current() -> Mapping[str, Any]:
    """Return the overrides active in this context, merged (empty when there are none)."""
    merged: dict[str, Any] = {}
    for layer in _layers.get():
        merged.update(layer.values)
    return MappingProxyType(merged)


def lookup(name: str) -> tuple[bool, Any]:
    """Return ``(True, value)`` if ``name`` is overridden here, otherwise ``(False, None)``."""
    # Overrides are keyed by keyword names, so only a string can be one; checking first also keeps an unhashable name
    # (a list, say) from raising here, before the caller's own name check.
    if isinstance(name, str):
        for layer in reversed(_layers.get()):
            if name in layer.values:
                return True, layer.values[name]
    return False, None


def push(values: Mapping[str, Any]) -> Token[tuple[Layer, ...]]:
    """Layer ``values`` over the active overrides; return the token that ``pop`` needs to undo it."""
    return _layers.set((*_layers.get(), Layer(MappingProxyType(dict(values)), pinned=False)))


def pop(token: Token[tuple[Layer, ...]]) -> None:
    """Undo the ``push`` that returned ``token``, keeping the layers pinned since."""
    layers = _layers.get()
    _layers.reset(token)
    before = _layers.get()
    # Of the layers added after the push, keep the pinned ones; a block opened since should have ended already.
    pinned_since = tuple(layer for layer in layers[len(before) + 1 :] if layer.pinned)
    if pinned_since:
        _layers.set((*before, *pinned_since))


def pin(values: Mapping[str, Any]) -> None:
    """Layer ``values`` over the active overrides, to stay when the blocks open now end."""
    _layers.set((*_layers.get(), Layer(MappingProxyType(dict(values)), pinned=True)))


def snapshot() -> tuple[Layer, ...]:
    """Return the layers active in this context, for ``restore``."""
    return _layers.get()


def restore(layers: tuple[Layer, ...]) -> None:
    """Make ``layers`` (from ``snapshot``) the active overrides, where push/pop can't pair up, as in pytest fixtures."""
    _layers.set(layers)
