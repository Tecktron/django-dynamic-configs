"""Constants that more than one module uses.

This module imports nothing from the package, so it can never be part of an import cycle. A constant used by one
module, or whose meaning one module owns, stays there.
"""

#: The deepest a ``json`` value may nest: each object or array is one level, so ``[[1]]`` is 2 levels deep. Python's
#: JSON reader and writer recurse once per level, and how deep they get before failing depends on the stack of the
#: thread doing it (thousands of levels in a main thread, a few hundred in a thread with a small stack), so this fixed
#: limit makes the same values work on every Python, machine and thread. Used by ``JSONSerializer`` to refuse deeper
#: values and by ``JSONTextarea``, which passes it to the admin's JSON editor in a data attribute.
JSON_MAX_DEPTH = 128

#: A set's help text, true whichever way its items are entered. Used by the set variant's registry entry and by the
#: set's form field.
SET_HELP = "No repeats."

#: The admin's optional script (``static/dynamic_configs/admin.js``); every page works without it. Used by the form
#: media in ``forms/config.py`` and by the admin's widgets.
ADMIN_SCRIPT = "dynamic_configs/admin.js"

#: The start of a list variant's type key, such as ``list:str``. Used to build the registry's variants and by the admin
#: to name a list type's check URL.
LIST_PREFIX = "list:"

#: The start of a set variant's type key, such as ``set:str``. Used like ``LIST_PREFIX``.
SET_PREFIX = "set:"
