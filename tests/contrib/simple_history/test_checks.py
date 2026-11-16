from django.apps import apps
from django.core import checks

from dynamic_configs.contrib.simple_history.checks import check_simple_history_installed


def test_the_sub_app_needs_simple_history_installed(mocker):
    mocker.patch.object(apps, "is_installed", return_value=False)
    [error] = check_simple_history_installed()
    assert (error.id, error.level) == ("dynamic_configs.E101", checks.ERROR)
    assert error.msg == (
        'dynamic_configs.contrib.simple_history is installed, but "simple_history" isn\'t in INSTALLED_APPS.'
    )
    assert error.hint == 'Add "simple_history" to INSTALLED_APPS.'


def test_with_simple_history_installed_there_is_no_error():
    assert check_simple_history_installed() == []


def test_uuid_history_ids_are_an_error(settings):
    settings.SIMPLE_HISTORY_HISTORY_ID_USE_UUID = True
    [error] = [message for message in checks.run_checks() if message.id.startswith("dynamic_configs.")]
    assert (error.id, error.level) == ("dynamic_configs.E102", checks.ERROR)
    assert error.msg == (
        "SIMPLE_HISTORY_HISTORY_ID_USE_UUID is set, but the config history's migration creates integer ids, so "
        "saving a config would fail."
    )
    assert error.hint == "Remove SIMPLE_HISTORY_HISTORY_ID_USE_UUID; the simple-history integration doesn't support it."


def test_integer_history_ids_are_no_error():
    assert not [message for message in checks.run_checks() if message.id.startswith("dynamic_configs.")]
