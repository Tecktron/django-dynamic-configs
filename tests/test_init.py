import importlib

import pytest
from django.apps import apps

import dynamic_configs


def test_version_matches_the_package_metadata():
    assert dynamic_configs.__version__ == "0.1.0"


def test_app_is_installed_with_a_readable_name():
    assert apps.get_app_config("dynamic_configs").verbose_name == "Dynamic configs"


def test_the_api_loads_lazily():
    api = importlib.import_module("dynamic_configs.api")
    assert dynamic_configs.get is api.get


def test_exceptions_are_importable_from_the_package():
    exceptions = importlib.import_module("dynamic_configs.exceptions")
    assert dynamic_configs.ConfigError is exceptions.ConfigError
    assert dynamic_configs.ConfigTypeError is exceptions.ConfigTypeError
    assert dynamic_configs.ConfigValueError is exceptions.ConfigValueError


def test_does_not_exist_is_importable_from_the_package():
    models = importlib.import_module("dynamic_configs.models")
    assert dynamic_configs.ConfigDoesNotExist is models.ConfigDoesNotExist


def test_unknown_attributes_raise_attribute_error():
    with pytest.raises(AttributeError, match="has no attribute 'nope'"):
        _ = dynamic_configs.nope
