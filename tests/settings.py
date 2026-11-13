"""Django settings for the test suite."""

import os
import tempfile
from pathlib import Path

from tests import real_cache

SECRET_KEY = "dynamic-configs-tests-not-a-secret"
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dynamic_configs",
    # Models and an admin for the browser tests.
    "tests.browser",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "tests.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
STATIC_URL = "/static/"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "dynamic-configs-tests"},
    "dummy": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
    "failing": {"BACKEND": "tests.failing_cache.FailingCache"},
}
USE_TZ = True
# A zone with daylight saving, so the datetime rules are exercised for real.
TIME_ZONE = "America/New_York"

if os.environ.get("DYNAMIC_CONFIGS_TEST_EXTRAS") == "1":
    # The django-simple-history integration, and the middleware that records who made a change.
    INSTALLED_APPS += ["simple_history", "dynamic_configs.contrib.simple_history"]
    MIDDLEWARE += ["simple_history.middleware.HistoryRequestMiddleware"]

if os.environ.get("DYNAMIC_CONFIGS_TEST_POSTGRES") == "1":
    # NAME only: the host, port, user and password come from libpq's PG* environment variables.
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "dynamic_configs"}}

if os.environ.get("DYNAMIC_CONFIGS_TEST_CACHE"):
    # A real server (tests/real_cache.py): an unknown value, or a missing address, stops here.
    CACHES["default"] = real_cache.cache_settings()
    # A file-backed SQLite test database, which a second process can open (the in-memory one can't be shared).
    shared_db = os.environ.get("DYNAMIC_CONFIGS_TEST_SHARED_DB")
    if shared_db:
        # The second process: it opens the first one's test database as its own.
        DATABASES["default"]["NAME"] = shared_db
    else:
        test_db = Path(tempfile.gettempdir()) / f"dynamic-configs-tests-{os.getpid()}.sqlite3"
        DATABASES["default"]["TEST"] = {"NAME": str(test_db)}
