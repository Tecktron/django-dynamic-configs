from django.apps import apps

import dynamic_configs


def test_version_matches_the_package_metadata():
    assert dynamic_configs.__version__ == "0.1.0"


def test_app_is_installed_with_a_readable_name():
    assert apps.get_app_config("dynamic_configs").verbose_name == "Dynamic configs"
