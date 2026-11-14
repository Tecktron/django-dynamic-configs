"""A second process for the cross-process test: reads settings through the shared cache and database.

Run as ``python -m tests.cross_process_reader`` with ``DYNAMIC_CONFIGS_TEST_CACHE`` and the cache's address set, and
``DYNAMIC_CONFIGS_TEST_SHARED_DB`` naming the first process's SQLite test database. For each setting name read from
standard input it prints one JSON line, ``{"get": <the value or None>, "cached": <repr of the cache entry>}``, until
standard input closes.
"""

import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django  # noqa: E402

django.setup()

import dynamic_configs  # noqa: E402
from dynamic_configs import cache  # noqa: E402

for line in sys.stdin:
    name = line.rstrip("\n")
    print(json.dumps({"get": dynamic_configs.get(name, default=None), "cached": repr(cache.read(name))}), flush=True)
