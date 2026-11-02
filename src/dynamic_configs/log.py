"""Logging helper with a re-entrancy guard.

A project's logging handler may itself read configs (for example to decide what to redact). If the cache or database
is down, that read would log a warning, which would call the handler again, and so on. The guard below stops logging
from this package while it is already logging in the current context, so that loop can't start.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

_logging_now: ContextVar[bool] = ContextVar("dynamic_configs_logging_now", default=False)


def log(
    logger: logging.Logger,
    level: int,
    message: str,
    *args: object,
    config_name: str | None = None,
    config_type: str | None = None,
    exc_info: bool = False,
) -> None:
    """Log ``message`` unless this package is already logging in the current context.

    Never pass a setting's value in ``message`` or ``args``: values may be secrets.

    :param logger: the module's logger
    :param level: a ``logging`` level, such as ``logging.WARNING``
    :param message: a ``%``-style format string
    :param args: arguments for ``message``
    :param config_name: the setting's name, added to the record as ``config_name``
    :param config_type: the setting's type key, added to the record as ``config_type``
    :param exc_info: attach the exception being handled
    """
    if _logging_now.get() or not logger.isEnabledFor(level):
        return
    extra: dict[str, str] = {}
    if config_name is not None:
        extra["config_name"] = config_name
    if config_type is not None:
        extra["config_type"] = config_type
    token = _logging_now.set(True)
    try:
        logger.log(level, message, *args, exc_info=exc_info, extra=extra)
    finally:
        _logging_now.reset(token)
