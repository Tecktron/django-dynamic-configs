"""Tests for the test settings' environment switches."""

import importlib

import pytest


@pytest.fixture
def reload_settings(monkeypatch):
    """Reload tests.settings with environment variables set, and reload it as it was afterwards."""
    module = importlib.import_module("tests.settings")
    # The real cache servers' environments set this; it changes DATABASES too, so the switches are checked without it.
    monkeypatch.delenv("DYNAMIC_CONFIGS_TEST_CACHE", raising=False)

    def reload(**environ):
        for name, value in environ.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(module)

    yield reload
    monkeypatch.undo()
    importlib.reload(module)


def test_postgres_is_chosen_by_an_environment_variable(reload_settings):
    """DYNAMIC_CONFIGS_TEST_POSTGRES selects PostgreSQL, with the connection left to libpq's variables."""
    settings = reload_settings(DYNAMIC_CONFIGS_TEST_POSTGRES="1")
    assert settings.DATABASES == {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "dynamic_configs"}}


def test_simple_history_is_turned_on_by_an_environment_variable(reload_settings):
    """DYNAMIC_CONFIGS_TEST_EXTRAS adds simple-history, its integration and its middleware."""
    settings = reload_settings(DYNAMIC_CONFIGS_TEST_EXTRAS="1")
    assert settings.INSTALLED_APPS[-2:] == ["simple_history", "dynamic_configs.contrib.simple_history"]
    assert settings.MIDDLEWARE[-1] == "simple_history.middleware.HistoryRequestMiddleware"
