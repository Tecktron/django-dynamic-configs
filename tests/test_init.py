import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.apps import apps

import dynamic_configs


def test_version_matches_the_package_metadata():
    # Compared with pyproject.toml rather than a literal, so the release workflow's dry run (a .devN build) passes too.
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    [version] = re.findall(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert dynamic_configs.__version__ == version


def test_app_is_installed_with_a_readable_name():
    assert apps.get_app_config("dynamic_configs").verbose_name == "Dynamic configs"


def test_importing_the_package_doesnt_import_models():
    # F24: run in a fresh interpreter without Django settings, where this test's own imports can't have loaded the
    # models already, and where importing them would raise.
    env = {name: value for name, value in os.environ.items() if name != "DJANGO_SETTINGS_MODULE"}
    code = "import sys, dynamic_configs; print(sorted(m for m in sys.modules if m.startswith('dynamic_configs')))"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)  # noqa: S603
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['dynamic_configs']"


def test_the_api_is_importable_from_the_package():
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
