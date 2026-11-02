"""Django settings for the test suite."""

SECRET_KEY = "dynamic-configs-tests-not-a-secret"
INSTALLED_APPS = ["dynamic_configs"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "dynamic-configs-tests"},
    "dummy": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}
USE_TZ = True
# A zone with daylight saving, so the datetime rules are exercised for real.
TIME_ZONE = "America/New_York"
